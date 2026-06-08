"""Realistic, capability-aware Mneno Core execution for the Context Rot Suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmarks.common.capabilities import detect_mneno_capabilities
from benchmarks.common.mneno_client import MnenoAdapter
from benchmarks.common.schema import (
    MnenoDecisionSummary,
    MnenoExecutionSummary,
    MnenoMemoryLoadRecord,
    MnenoResult,
    RunStatus,
    TraceSummary,
)
from benchmarks.common.traces import TraceLoader
from benchmarks.common.utils import save_json
from benchmarks.mneno_suite.dataset import MnenoSuiteCase, MnenoSuiteDataset
from benchmarks.mneno_suite.trace_analysis import (
    extract_conflict_events,
    extract_exclusion_reasons,
    extract_hierarchy_events,
    extract_inclusion_reasons,
    extract_memory_decisions,
    extract_session_events,
)


@dataclass
class MnenoRuntime:
    adapter: MnenoAdapter
    client: Any
    summary: MnenoExecutionSummary
    reverse_id_map: dict[str, str] = field(default_factory=dict)
    session_id_map: dict[str, str] = field(default_factory=dict)
    compaction_kept_ids: list[str] | None = None
    setup_trace_ids: list[str] = field(default_factory=list)


@dataclass
class MnenoCaseExecution:
    result: MnenoResult
    metric_ids: list[str]
    compacted_ids: list[str] | None
    explainability_available: bool
    hierarchy_available: bool
    session_context_available: bool


def initialize_mneno_runtime(
    adapter: MnenoAdapter,
    dataset: MnenoSuiteDataset,
    results_dir: Path,
    run_id: str,
) -> MnenoRuntime:
    client = adapter.create_client(trace_enabled=True)
    report = detect_mneno_capabilities(adapter, client)
    summary = MnenoExecutionSummary(capability_report=report)
    runtime = MnenoRuntime(adapter=adapter, client=client, summary=summary)

    session_ids = sorted(
        {memory.session_id for memory in dataset.memories if memory.session_id}
    )
    if report.capabilities.get("create_session"):
        for session_id in session_ids:
            try:
                session = adapter.create_session(
                    client=client,
                    session_id=session_id,
                    id=session_id,
                    title=f"Synthetic session {session_id}",
                    metadata={"dataset_session_id": session_id},
                )
                internal_session_id = _internal_session_id(session) or session_id
                runtime.session_id_map[session_id] = internal_session_id
                summary.session_id_map[session_id] = internal_session_id
                summary.sessions_created += 1
            except Exception as exc:
                summary.capability_errors["create_session"] = str(exc)
                break

    ordered = sorted(
        dataset.memories,
        key=lambda memory: (
            memory.session_id or "",
            memory.sequence_index if memory.sequence_index is not None else -1,
            memory.id,
        ),
    )
    for memory in ordered:
        payload = memory.as_benchmark_memory()
        if memory.session_id:
            payload["session_id"] = runtime.session_id_map.get(
                memory.session_id, memory.session_id
            )
        conflict_reports: list[dict[str, Any]] = []
        resolution_actions: list[dict[str, Any] | str] = []
        insertion_trace_ids: list[str] = []
        if report.capabilities.get("add_with_report"):
            try:
                raw = adapter.add_with_report(client, payload)
                conflict_reports = _conflicts(raw)
                resolution_actions = _resolution_actions(raw)
                insertion_trace_ids = _trace_ids(raw)
                summary.conflicts_detected += len(conflict_reports)
                runtime.setup_trace_ids.extend(insertion_trace_ids)
            except Exception as exc:
                summary.capability_errors["add_with_report"] = str(exc)
                raw = adapter.add_memory(client, payload)
        else:
            raw = adapter.add_memory(client, payload)
        internal_id = _internal_memory_id(raw) or memory.id
        summary.memory_id_map[memory.id] = internal_id
        runtime.reverse_id_map[internal_id] = memory.id
        summary.memory_loads.append(
            MnenoMemoryLoadRecord(
                dataset_memory_id=memory.id,
                mneno_memory_id=internal_id,
                conflict_reports=conflict_reports,
                resolution_actions=resolution_actions,
                trace_ids=insertion_trace_ids,
            )
        )
        summary.memories_loaded += 1

    if report.capabilities.get("evaluate_hierarchy"):
        try:
            hierarchy = adapter.evaluate_hierarchy(client=client)
            summary.hierarchy_evaluated = True
            summary.hierarchy_transitions = _transition_counts(hierarchy)
            runtime.setup_trace_ids.extend(_trace_ids(hierarchy))
            _save_setup_export(results_dir, run_id, "hierarchy", hierarchy)
        except Exception as exc:
            summary.capability_errors["evaluate_hierarchy"] = str(exc)

    if report.capabilities.get("preview_compaction"):
        try:
            preview = adapter.preview_compaction(
                client=client, mutate=False, dry_run=True
            )
            summary.compaction_previewed = True
            summary.compaction_stats = _compaction_stats(preview)
            runtime.compaction_kept_ids = _normalize_ids(
                _ids_from_raw(preview, ("kept", "kept_ids", "retained_memory_ids")),
                runtime.reverse_id_map,
            )
            runtime.setup_trace_ids.extend(_trace_ids(preview))
            _save_setup_export(results_dir, run_id, "compaction-preview", preview)
        except Exception as exc:
            summary.capability_errors["preview_compaction"] = str(exc)

    runtime.setup_trace_ids = sorted(set(runtime.setup_trace_ids))
    if report.capabilities.get("export_trace"):
        for index, trace_id in enumerate(runtime.setup_trace_ids):
            try:
                trace_export = adapter.export_trace(trace_id=trace_id, client=client)
                save_json(
                    results_dir
                    / "mneno"
                    / "traces"
                    / f"{run_id}-setup-{index + 1}.json",
                    trace_export,
                )
                summary.traces_exported += 1
            except Exception as exc:
                summary.capability_errors["export_trace"] = str(exc)
                break
    return runtime


def execute_mneno_case(
    runtime: MnenoRuntime,
    case: MnenoSuiteCase,
    results_dir: Path,
    run_id: str,
    limit: int,
) -> MnenoCaseExecution:
    adapter = runtime.adapter
    client = runtime.client
    capabilities = runtime.summary.capability_report.capabilities
    common = {
        "client": client,
        "query": case.query,
        "expected_memory_ids": _to_internal(case.expected_memory_ids, runtime),
        "relevant_memory_ids": _to_internal(case.expected_memory_ids, runtime),
        "forbidden_memory_ids": _to_internal(case.forbidden_memory_ids, runtime),
        "current_session_id": _internal_session_id_for_case(case, runtime),
        "session_id": _internal_session_id_for_case(case, runtime),
        "budget": case.budget,
        "limit": limit,
        "k": limit,
    }

    try:
        search = adapter.evaluate_search(**common)
        context = None
        if capabilities.get("evaluate_context"):
            try:
                context = adapter.evaluate_context(**common)
            except Exception as exc:
                runtime.summary.capability_errors["evaluate_context"] = str(exc)
        built_context = None
        if capabilities.get("build_context"):
            try:
                built_context = adapter.build_context(**common)
            except Exception as exc:
                runtime.summary.capability_errors["build_context"] = str(exc)
        compaction = None
        if case.category == "compaction_retention" and capabilities.get(
            "evaluate_compaction"
        ):
            try:
                compaction = adapter.evaluate_compaction(**common)
            except Exception as exc:
                runtime.summary.capability_errors["evaluate_compaction"] = str(exc)

        retrieved_ids = _normalize_ids(
            _ids_from_raw(
                search.raw_result,
                ("retrieved_memory_ids", "selected_memory_ids", "memory_ids", "ids"),
            ),
            runtime.reverse_id_map,
        )
        included_ids = _normalize_ids(
            _ids_from_raw(
                built_context,
                (
                    "included_memory_ids",
                    "included_ids",
                    "included",
                    "memory_ids",
                    "ids",
                ),
            ),
            runtime.reverse_id_map,
        )
        excluded_ids = _normalize_ids(
            _ids_from_raw(
                built_context, ("excluded_memory_ids", "excluded_ids", "excluded")
            ),
            runtime.reverse_id_map,
        )
        metric_ids = included_ids or retrieved_ids
        compacted_ids = runtime.compaction_kept_ids
        if compaction is not None:
            compacted_ids = (
                _normalize_ids(
                    _ids_from_raw(
                        compaction.raw_result,
                        ("compacted_memory_ids", "retained_memory_ids", "kept_ids"),
                    ),
                    runtime.reverse_id_map,
                )
                or compacted_ids
            )

        trace_ids = sorted(
            set(
                _trace_ids(search.raw_result)
                + ([search.trace_id] if search.trace_id else [])
                + (_trace_ids(context.raw_result) if context else [])
                + ([context.trace_id] if context and context.trace_id else [])
                + _trace_ids(built_context)
                + (_trace_ids(compaction.raw_result) if compaction else [])
                + ([compaction.trace_id] if compaction and compaction.trace_id else [])
            )
        )
        traces: list[Any] = []
        trace_summaries: list[TraceSummary] = []
        for index, trace_id in enumerate(trace_ids):
            if not capabilities.get("export_trace"):
                break
            try:
                trace_export = adapter.export_trace(trace_id=trace_id, client=client)
            except Exception as exc:
                runtime.summary.capability_errors["export_trace"] = str(exc)
                break
            traces.append(trace_export)
            trace_path = (
                results_dir
                / "mneno"
                / "traces"
                / f"{run_id}-{case.id}-{index + 1}.json"
            )
            save_json(trace_path, trace_export)
            runtime.summary.traces_exported += 1
            if (
                isinstance(trace_export, dict)
                and trace_export.get("format") == "mneno.trace"
            ):
                summary = TraceLoader().load_trace_export(trace_export)
                summary.raw_trace_reference = str(trace_path)
                trace_summaries.append(summary)

        decision_summary = _decision_summary(
            retrieved_ids, included_ids, excluded_ids, trace_ids, traces, runtime
        )
        benchmark_path: Path | None = None
        try:
            if adapter.supports("build_evaluation_report", client=client):
                raw_metrics = search.raw_result.get("metrics", [])
                report = adapter.call_optional(
                    "build_evaluation_report",
                    client=client,
                    benchmark_name=f"mneno-context-rot:{case.id}",
                    metrics=raw_metrics,
                    trace_ids=trace_ids,
                    summary=case.expected_behavior,
                    metadata={"case_id": case.id, "category": case.category},
                )
                benchmark_export = adapter.export_benchmark(
                    report=report,
                    client=client,
                    include_traces=True,
                    metadata={"case_id": case.id, "category": case.category},
                )
            else:
                benchmark_export = adapter.export_benchmark(
                    result=search.raw_result,
                    evaluation=search.raw_result,
                    client=client,
                )
            benchmark_path = (
                results_dir / "mneno" / "exports" / f"{run_id}-{case.id}.json"
            )
            save_json(benchmark_path, benchmark_export)
        except Exception as exc:
            runtime.summary.capability_errors["export_benchmark_result"] = str(exc)
            benchmark_path = None

        return MnenoCaseExecution(
            result=MnenoResult(
                status=RunStatus.COMPLETED,
                retrieved_memory_ids=retrieved_ids,
                included_memory_ids=included_ids,
                excluded_memory_ids=excluded_ids,
                trace_ids=trace_ids,
                decision_summary=decision_summary,
                trace_summary=_merge_trace_summaries(trace_summaries),
                latency_ms=float(search.metrics.get("latency_ms") or 0.0),
                metadata={
                    "category": case.category,
                    "benchmark_export": str(benchmark_path) if benchmark_path else None,
                    "search_evaluation": search.model_dump(mode="json"),
                    "context_evaluation": (
                        context.model_dump(mode="json") if context else None
                    ),
                    "build_context": built_context,
                    "compaction_evaluation": (
                        compaction.model_dump(mode="json") if compaction else None
                    ),
                    "compacted_memory_ids": compacted_ids,
                },
            ),
            metric_ids=metric_ids,
            compacted_ids=compacted_ids,
            explainability_available=bool(traces),
            hierarchy_available=runtime.summary.hierarchy_evaluated,
            session_context_available=built_context is not None,
        )
    except Exception as exc:
        return MnenoCaseExecution(
            result=MnenoResult(status=RunStatus.FAILED, error=str(exc)),
            metric_ids=[],
            compacted_ids=runtime.compaction_kept_ids,
            explainability_available=False,
            hierarchy_available=runtime.summary.hierarchy_evaluated,
            session_context_available=False,
        )


def _decision_summary(
    retrieved_ids: list[str],
    included_ids: list[str],
    excluded_ids: list[str],
    trace_ids: list[str],
    traces: list[Any],
    runtime: MnenoRuntime,
) -> MnenoDecisionSummary:
    inclusion: dict[str, list[str]] = {}
    exclusion: dict[str, list[str]] = {}
    conflicts: list[dict[str, Any]] = []
    hierarchy: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    for trace in traces:
        extract_memory_decisions(trace)
        inclusion.update(
            _normalize_reason_map(extract_inclusion_reasons(trace), runtime)
        )
        exclusion.update(
            _normalize_reason_map(extract_exclusion_reasons(trace), runtime)
        )
        conflicts.extend(extract_conflict_events(trace))
        hierarchy.extend(extract_hierarchy_events(trace))
        sessions.extend(extract_session_events(trace))
    return MnenoDecisionSummary(
        retrieved_ids=retrieved_ids,
        included_ids=included_ids,
        excluded_ids=excluded_ids,
        trace_ids=trace_ids,
        inclusion_reasons=inclusion,
        exclusion_reasons=exclusion,
        conflict_events=conflicts,
        hierarchy_events=hierarchy,
        session_events=sessions,
    )


def _normalize_reason_map(
    reasons: dict[str, list[str]], runtime: MnenoRuntime
) -> dict[str, list[str]]:
    return {
        runtime.reverse_id_map.get(memory_id, memory_id): values
        for memory_id, values in reasons.items()
    }


def _normalize_ids(ids: list[str], reverse_map: dict[str, str]) -> list[str]:
    return list(
        dict.fromkeys(reverse_map.get(memory_id, memory_id) for memory_id in ids)
    )


def _to_internal(ids: list[str], runtime: MnenoRuntime) -> list[str]:
    return [
        runtime.summary.memory_id_map.get(memory_id, memory_id) for memory_id in ids
    ]


def _internal_memory_id(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("memory_id", "id", "internal_memory_id"):
            value = raw.get(key)
            if value is not None:
                return str(value)
        for key in ("memory", "result", "added_memory"):
            value = _internal_memory_id(raw.get(key))
            if value:
                return value
    return None


def _internal_session_id(raw: Any) -> str | None:
    if isinstance(raw, dict):
        value = raw.get("id") or raw.get("session_id")
        return str(value) if value is not None else None
    return None


def _internal_session_id_for_case(
    case: MnenoSuiteCase, runtime: MnenoRuntime
) -> str | None:
    if case.current_session_id is None:
        return None
    return runtime.session_id_map.get(case.current_session_id, case.current_session_id)


def _ids_from_raw(
    raw: Any,
    keys: tuple[str, ...] = (
        "retrieved_memory_ids",
        "included_memory_ids",
        "memory_ids",
        "ids",
    ),
) -> list[str]:
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json")
    if isinstance(raw, dict):
        for key in keys:
            value = raw.get(key)
            if isinstance(value, list):
                return _ids_from_items(value)
        for key in ("result", "results", "memories", "context", "items", "preview"):
            nested = raw.get(key)
            ids = _ids_from_raw(nested, keys)
            if ids:
                return ids
    if isinstance(raw, list):
        return _ids_from_items(raw)
    return []


def _ids_from_items(items: list[Any]) -> list[str]:
    ids: list[str] = []
    for item in items:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            value = (
                item.get("memory_id") or item.get("id") or item.get("dataset_memory_id")
            )
            if value is not None:
                ids.append(str(value))
    return ids


def _trace_ids(raw: Any) -> list[str]:
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json")
    if not isinstance(raw, dict):
        return []
    ids: list[str] = []
    for key in ("trace_id", "add_trace_id", "evaluation_trace_id"):
        value = raw.get(key)
        if value is not None:
            ids.append(str(value))
    trace = raw.get("trace")
    if isinstance(trace, dict):
        value = trace.get("id") or trace.get("trace_id")
        if value is not None:
            ids.append(str(value))
    return ids


def _conflicts(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    for key in ("conflicts", "conflict_reports", "detected_conflicts"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _resolution_actions(raw: Any) -> list[dict[str, Any] | str]:
    if not isinstance(raw, dict):
        return []
    for key in ("resolution_actions", "actions", "resolutions"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, (dict, str))]
    return []


def _transition_counts(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    counts: dict[str, int] = {}
    for key in ("promoted", "demoted", "archived", "expired"):
        value = raw.get(key)
        if isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, int):
            counts[key] = value
    stats = raw.get("stats")
    if isinstance(stats, dict):
        for key, value in stats.items():
            if isinstance(value, int):
                counts[str(key)] = value
    return counts


def _compaction_stats(raw: Any) -> dict[str, int | float]:
    if not isinstance(raw, dict):
        return {}
    stats: dict[str, int | float] = {}
    for key in ("kept", "merged", "discarded"):
        value = raw.get(key)
        if isinstance(value, list):
            stats[key] = len(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            stats[key] = value
    nested = raw.get("stats")
    if isinstance(nested, dict):
        for key, value in nested.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                stats[str(key)] = value
    return stats


def _merge_trace_summaries(summaries: list[TraceSummary]) -> TraceSummary | None:
    if not summaries:
        return None
    return TraceSummary(
        trace_id=summaries[0].trace_id,
        operation_count=sum(item.operation_count for item in summaries),
        event_count=sum(item.event_count for item in summaries),
        decision_count=sum(item.decision_count for item in summaries),
        duration_ms=sum(item.duration_ms or 0.0 for item in summaries),
        retrieved_memory_ids=list(
            dict.fromkeys(
                value for item in summaries for value in item.retrieved_memory_ids
            )
        ),
        selected_memory_ids=list(
            dict.fromkeys(
                value for item in summaries for value in item.selected_memory_ids
            )
        ),
        suppressed_memory_ids=list(
            dict.fromkeys(
                value for item in summaries for value in item.suppressed_memory_ids
            )
        ),
        conflict_resolutions=list(
            dict.fromkeys(
                value for item in summaries for value in item.conflict_resolutions
            )
        ),
        lifecycle_events=list(
            dict.fromkeys(
                value for item in summaries for value in item.lifecycle_events
            )
        ),
        explanations=list(
            dict.fromkeys(value for item in summaries for value in item.explanations)
        ),
        raw_trace_reference=summaries[0].raw_trace_reference,
    )


def _save_setup_export(results_dir: Path, run_id: str, name: str, value: Any) -> None:
    save_json(results_dir / "mneno" / "exports" / f"{run_id}-{name}.json", value)
