"""Run the external LOCOMO benchmark pipeline without fabricating QA scores."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from benchmarks.common.baselines import full_context_baseline, keyword_baseline
from benchmarks.common.llm_client import LLMClient
from benchmarks.common.mneno_client import INSTALL_MESSAGE, MnenoAdapter
from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRun,
    MetricResult,
    MnenoResult,
    NormalizedContextResult,
    NormalizedSearchResult,
    RunStatus,
    TraceSummary,
)
from benchmarks.common.traces import TraceLoader
from benchmarks.common.utils import estimate_tokens, generate_run_id, now_iso, save_json
from benchmarks.locomo.answering import AnswerCandidate, generate_answer_from_context
from benchmarks.locomo.config import LOCOMOEvaluationConfig, LOCOMOEvaluationMode
from benchmarks.locomo.judge import JudgeResult, LOCOMOJudge
from benchmarks.locomo.loader import load_locomo_dataset
from benchmarks.locomo.metrics import (
    OFFICIAL_SCORING_PENDING,
    aggregate_metric_maps,
    answer_diagnostic_score,
    contains_answer,
    evidence_precision,
    evidence_recall,
    exact_match,
    normalized_exact_match,
    official_locomo_qa_score,
    official_metric_placeholders,
    retrieval_hit_rate,
    token_f1,
)
from benchmarks.locomo.normalization import NormalizedLOCOMOResult
from benchmarks.locomo.schema import LOCOMOConversation, LOCOMODataset, LOCOMOQuestion
from benchmarks.locomo.validator import LOCOMODatasetMissingError
from benchmarks.locomo.validator import locomo_validation_warnings

app = typer.Typer(add_completion=False)
console = Console()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_VERSION = "0.6.0"
SUITE_NAME = "LOCOMO"
SYSTEMS = ["keyword_baseline", "full_context_baseline", "mneno"]
CATEGORY_NAMES = {
    1: "factual_recall",
    2: "temporal_reasoning",
    3: "multi_hop_reasoning",
    4: "open_domain",
    5: "adversarial",
}


def run_locomo(
    data_dir: Path,
    results_dir: Path,
    k: int = 5,
    adapter: MnenoAdapter | None = None,
    config_path: Path | None = None,
    evaluation_config: LOCOMOEvaluationConfig | None = None,
    judge: LOCOMOJudge | None = None,
) -> BenchmarkRun:
    """Execute LOCOMO loading, retrieval, normalization, and reporting."""

    config = _load_config(config_path, k, evaluation_config)
    run = _new_run(config, adapter)
    result_path = results_dir / "locomo" / "locomo_latest.json"
    report_path = results_dir / "locomo" / "locomo_latest.md"

    try:
        dataset = load_locomo_dataset(
            _resolve_data_dir(data_dir),
            allow_malformed_evidence=config.allow_malformed_evidence,
        )
    except LOCOMODatasetMissingError as exc:
        return _finish_missing_dataset(run, result_path, report_path, str(exc))

    sdk = adapter or MnenoAdapter()
    mneno_available = sdk.is_available()
    if mneno_available:
        run.mneno_version = sdk.version()
    metrics_by_system: dict[str, list[dict[str, float | int | None]]] = defaultdict(
        list
    )
    judge_status_by_system: dict[str, list[str]] = defaultdict(list)
    trace_ids_by_system: dict[str, list[str]] = defaultdict(list)
    system_errors: dict[str, list[str]] = defaultdict(list)
    validation_warnings = _validation_warnings(dataset)
    locomo_judge = judge or _build_judge(config, results_dir, run.run_id)
    case_counter = 0

    for conversation in dataset.conversations:
        memories = [
            message.as_benchmark_memory(conversation.id)
            for message in conversation.messages
        ]
        runtime = (
            _initialize_mneno_conversation(sdk, conversation, memories)
            if mneno_available
            else None
        )
        for question in conversation.questions:
            if config.max_cases is not None and case_counter >= config.max_cases:
                break
            case_counter += 1
            baseline_results: list[BaselineResult] = []
            case_metrics: dict[str, list[MetricResult]] = {}

            for system, baseline in (
                ("keyword_baseline", keyword_baseline),
                ("full_context_baseline", full_context_baseline),
            ):
                raw = baseline(memories, question.question, k=k)
                retrieved_ids = _search_ids(raw)
                values = _retrieval_metrics(retrieved_ids, question)
                answer = _answer_for_mode(
                    config,
                    system,
                    question,
                    _context_text(memories, retrieved_ids),
                )
                judge_result = _judge_for_mode(
                    config,
                    locomo_judge,
                    question,
                    answer,
                    results_dir,
                    run.run_id,
                    system,
                )
                _apply_answer_metrics(values, question, answer, judge_result, config)
                if judge_result is not None:
                    judge_status_by_system[system].append(judge_result.status)
                metrics_by_system[system].append(values)
                normalized = _normalized_result(
                    system,
                    question,
                    values,
                    retrieved_ids=retrieved_ids,
                    answer=answer,
                    judge_result=judge_result,
                )
                baseline_results.append(
                    BaselineResult(
                        name=system,
                        retrieved_memory_ids=retrieved_ids,
                        context_tokens=_context_tokens(memories, retrieved_ids),
                        latency_ms=float(raw.metrics.get("latency_ms") or 0.0),
                        metadata={
                            "conversation_id": conversation.id,
                            "category": question.category,
                            "normalized_result": raw.model_dump(mode="json"),
                            "locomo_result": normalized.model_dump(mode="json"),
                            "answer_candidate": answer.model_dump(mode="json")
                            if answer
                            else None,
                            "judge_result": judge_result.model_dump(mode="json")
                            if judge_result
                            else None,
                        },
                    )
                )
                case_metrics[system] = _metric_results(values)

            if not mneno_available:
                mneno_result = MnenoResult(
                    status=RunStatus.SKIPPED,
                    skip_reason=INSTALL_MESSAGE,
                    metadata={"conversation_id": conversation.id},
                )
                case_metrics["mneno"] = official_metric_placeholders()
            elif runtime is None:
                reason = "Mneno conversation initialization failed."
                mneno_result = MnenoResult(
                    status=RunStatus.FAILED,
                    error=reason,
                    metadata={"conversation_id": conversation.id},
                )
                system_errors["mneno"].append(reason)
                case_metrics["mneno"] = official_metric_placeholders()
            else:
                mneno_result, values, normalized = _execute_mneno_question(
                    sdk,
                    runtime,
                    conversation,
                    question,
                    memories,
                    results_dir,
                    run.run_id,
                    k,
                    config,
                    locomo_judge,
                )
                case_metrics["mneno"] = _metric_results(values)
                mneno_result.metadata["locomo_result"] = normalized.model_dump(
                    mode="json"
                )
                if mneno_result.status == RunStatus.COMPLETED:
                    metrics_by_system["mneno"].append(values)
                    trace_ids_by_system["mneno"].extend(normalized.trace_ids)
                    judge_result = normalized.metadata.get("judge_result")
                    if isinstance(judge_result, dict):
                        judge_status_by_system["mneno"].append(
                            str(judge_result.get("status", "unknown"))
                        )
                elif mneno_result.error:
                    system_errors["mneno"].append(mneno_result.error)

            run.results.append(
                BenchmarkResult(
                    case=_benchmark_case(question),
                    baseline_results=baseline_results,
                    mneno_result=mneno_result,
                    metrics=case_metrics,
                )
            )
        if config.max_cases is not None and case_counter >= config.max_cases:
            break

    summary = _build_summary(
        dataset,
        metrics_by_system,
        trace_ids_by_system,
        judge_status_by_system,
        system_errors,
        mneno_available,
        config,
        validation_warnings,
        result_path,
        report_path,
        run,
    )
    run.export_metadata["locomo"] = summary
    run.export_metadata["mneno_status"] = summary["systems"]["mneno"]["status"]
    for system, metric_rows in metrics_by_system.items():
        run.summary_metrics[system] = _metric_results(
            aggregate_metric_maps(metric_rows)
        )
    if not mneno_available:
        run.summary_metrics["mneno"] = official_metric_placeholders()
    run.status = RunStatus.COMPLETED
    run.finished_at = now_iso()
    save_json(result_path, run.model_dump(mode="json"))
    _write_report(run, report_path)
    console.print(f"[green]Result:[/green] {result_path}")
    console.print(f"[green]Report:[/green] {report_path}")
    return run


def _new_run(
    config: LOCOMOEvaluationConfig, adapter: MnenoAdapter | None = None
) -> BenchmarkRun:
    sdk = adapter or MnenoAdapter()
    available = sdk.is_available()
    return BenchmarkRun(
        benchmark_version=BENCHMARK_VERSION,
        mneno_version=sdk.version() if available else None,
        run_id=generate_run_id("locomo"),
        suite="locomo",
        status=RunStatus.RUNNING,
        started_at=now_iso(),
        systems=SYSTEMS,
        config=config.model_dump(mode="json"),
        export_metadata={
            "format": "mneno-bench.locomo",
            "version": 1,
            "suite_name": SUITE_NAME,
            "evaluation_mode": config.mode,
        },
    )


def _finish_missing_dataset(
    run: BenchmarkRun, result_path: Path, report_path: Path, reason: str
) -> BenchmarkRun:
    run.status = RunStatus.DATASET_MISSING
    run.finished_at = now_iso()
    run.errors = []
    run.export_metadata["locomo"] = {
        "dataset_status": RunStatus.DATASET_MISSING.value,
        "execution_status": RunStatus.SKIPPED.value,
        "evaluation_mode": run.config.get("mode", "retrieval_only"),
        "skip_reason": reason,
        "dataset": {
            "source_path": None,
            "conversation_count": 0,
            "message_count": 0,
            "question_count": 0,
            "categories": {},
        },
        "systems": {
            system: {
                "status": RunStatus.SKIPPED.value,
                "metrics": {},
                "score_labels": _empty_score_labels(),
                "trace_ids": [],
                "judge": {"status": "skipped", "reason": "Dataset missing."},
                "skip_reason": "LOCOMO dataset is not installed.",
            }
            for system in SYSTEMS
        },
        "official_scoring": {
            "status": "unavailable",
            "reason": "Dataset missing.",
        },
        "result_path": str(result_path),
        "report_path": str(report_path),
        "trace_directory": str(result_path.parent / "traces"),
        "raw_output_directory": str(result_path.parent / "raw"),
        "judge_prompt_directory": str(result_path.parent / "judge" / "prompts"),
        "judge_response_directory": str(result_path.parent / "judge" / "responses"),
    }
    save_json(result_path, run.model_dump(mode="json"))
    _write_report(run, report_path)
    console.print("[yellow]LOCOMO dataset missing; wrote a skipped report.[/yellow]")
    return run


def _initialize_mneno_conversation(
    sdk: MnenoAdapter,
    conversation: LOCOMOConversation,
    memories: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        client = sdk.create_client(trace_enabled=True)
        id_map: dict[str, str] = {}
        session_id_map: dict[str, str] = {}
        if sdk.supports("create_session", client=client):
            for session_id in sorted(
                {
                    str(memory["session_id"])
                    for memory in memories
                    if memory.get("session_id")
                }
            ):
                try:
                    session = sdk.create_session(
                        client=client,
                        session_id=session_id,
                        id=session_id,
                        title=f"LOCOMO session {session_id}",
                        metadata={
                            "benchmark": "locomo",
                            "conversation_id": conversation.id,
                        },
                    )
                    internal_id = _value(session, "session_id") or _value(session, "id")
                    session_id_map[session_id] = str(internal_id or session_id)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    break
        for memory in memories:
            payload = dict(memory)
            dataset_id = str(payload["id"])
            raw_session_id = payload.get("session_id")
            if raw_session_id is not None:
                payload["session_id"] = session_id_map.get(
                    str(raw_session_id), str(raw_session_id)
                )
            if sdk.supports("add_with_report", client=client):
                report = sdk.add_with_report(client, payload)
                internal_id = _value(report, "memory_id") or _value(report, "id")
                id_map[dataset_id] = str(internal_id or dataset_id)
            else:
                raw = sdk.add_memory(client, payload)
                internal_id = _value(raw, "memory_id") or _value(raw, "id")
                id_map[dataset_id] = str(internal_id or dataset_id)
        return {
            "client": client,
            "id_map": id_map,
            "reverse_id_map": {value: key for key, value in id_map.items()},
            "session_id_map": session_id_map,
            "conversation_id": conversation.id,
        }
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _execute_mneno_question(
    sdk: MnenoAdapter,
    runtime: dict[str, Any],
    conversation: LOCOMOConversation,
    question: LOCOMOQuestion,
    memories: list[dict[str, Any]],
    results_dir: Path,
    run_id: str,
    k: int,
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
) -> tuple[MnenoResult, dict[str, float | int | None], NormalizedLOCOMOResult]:
    client = runtime["client"]
    reverse_id_map = runtime["reverse_id_map"]
    if not sdk.supports("evaluate_search", client=client):
        result = MnenoResult(
            status=RunStatus.SKIPPED,
            skip_reason="Installed Mneno does not expose evaluate_search().",
            metadata={"conversation_id": conversation.id},
        )
        values = _retrieval_metrics([], question)
        return result, values, _normalized_result("mneno", question, values)

    try:
        search = sdk.evaluate_search(
            client=client,
            query=question.question,
            expected_memory_ids=question.evidence_ids,
            k=k,
            limit=k,
        )
        context: NormalizedContextResult | None = None
        if sdk.supports("evaluate_context", client=client):
            context = sdk.evaluate_context(
                client=client,
                query=question.question,
                expected_memory_ids=question.evidence_ids,
                expected_answer=question.expected_answers,
            )
        built_context: Any = None
        if sdk.supports("build_context", client=client):
            built_context = sdk.build_context(
                client=client,
                query=question.question,
                expected_memory_ids=question.evidence_ids,
                forbidden_memory_ids=[],
                limit=k,
            )

        retrieved_ids = _normalize_ids(_search_ids(search), reverse_id_map)
        included_ids = _normalize_ids(
            _strings(_value(built_context, "included_memory_ids", [])), reverse_id_map
        )
        metric_ids = included_ids or retrieved_ids
        trace_ids = _unique_strings(
            [
                search.trace_id,
                context.trace_id if context is not None else None,
                _value(built_context, "trace_id"),
            ]
        )
        trace_summary, trace_locations = _export_traces(
            sdk,
            client,
            trace_ids,
            results_dir,
            run_id,
            question.id,
        )
        values = _retrieval_metrics(metric_ids, question)
        answer = _answer_for_mode(
            config,
            "mneno",
            question,
            _context_text(memories, metric_ids),
            trace_ids=trace_ids,
            metadata={"context_source": "mneno_built_context_or_search"},
        )
        judge_result = _judge_for_mode(
            config,
            judge,
            question,
            answer,
            results_dir,
            run_id,
            "mneno",
        )
        _apply_answer_metrics(values, question, answer, judge_result, config)
        raw_output = {
            "search": search.model_dump(mode="json"),
            "context": context.model_dump(mode="json") if context else None,
            "built_context": built_context,
            "retrieved_dialog_ids": retrieved_ids,
            "included_dialog_ids": included_ids,
            "trace_locations": trace_locations,
            "answer_candidate": answer.model_dump(mode="json") if answer else None,
            "judge_result": judge_result.model_dump(mode="json")
            if judge_result
            else None,
        }
        raw_path = (
            results_dir / "locomo" / "raw" / run_id / f"{_safe_name(question.id)}.json"
        )
        save_json(raw_path, raw_output)
        normalized = _normalized_result(
            "mneno",
            question,
            values,
            retrieved_ids=metric_ids,
            trace_ids=trace_ids,
            answer=answer,
            judge_result=judge_result,
            metadata={"raw_output_path": str(raw_path)},
        )
        return (
            MnenoResult(
                status=RunStatus.COMPLETED,
                retrieved_memory_ids=retrieved_ids,
                included_memory_ids=included_ids,
                context_tokens=_context_tokens(memories, metric_ids),
                latency_ms=float(search.metrics.get("latency_ms") or 0.0),
                trace_summary=trace_summary,
                trace_ids=trace_ids,
                metadata={
                    "conversation_id": conversation.id,
                    "raw_output_path": str(raw_path),
                    "trace_locations": trace_locations,
                    "answer_candidate": answer.model_dump(mode="json")
                    if answer
                    else None,
                    "judge_result": judge_result.model_dump(mode="json")
                    if judge_result
                    else None,
                },
            ),
            values,
            normalized,
        )
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        values = _retrieval_metrics([], question)
        normalized = _normalized_result(
            "mneno", question, values, metadata={"error": str(exc)}
        )
        return (
            MnenoResult(
                status=RunStatus.FAILED,
                error=str(exc),
                metadata={"conversation_id": conversation.id},
            ),
            values,
            normalized,
        )


def _export_traces(
    sdk: MnenoAdapter,
    client: Any,
    trace_ids: list[str],
    results_dir: Path,
    run_id: str,
    question_id: str,
) -> tuple[TraceSummary | None, list[str]]:
    if not trace_ids or not sdk.supports("export_trace", client=client):
        return None, []
    summaries: list[TraceSummary] = []
    locations: list[str] = []
    for trace_id in trace_ids:
        try:
            raw_trace = sdk.export_trace(client=client, trace_id=trace_id)
            path = (
                results_dir
                / "locomo"
                / "traces"
                / f"{run_id}-{_safe_name(question_id)}-{_safe_name(trace_id)}.json"
            )
            save_json(path, raw_trace)
            locations.append(str(path))
            summaries.append(TraceLoader().load_trace(raw_trace))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
    return (_merge_trace_summaries(summaries) if summaries else None), locations


def _merge_trace_summaries(summaries: list[TraceSummary]) -> TraceSummary:
    return TraceSummary(
        trace_id=summaries[0].trace_id,
        operation_count=sum(item.operation_count for item in summaries),
        event_count=sum(item.event_count for item in summaries),
        decision_count=sum(item.decision_count for item in summaries),
        duration_ms=(
            round(
                sum(item.duration_ms or 0.0 for item in summaries),
                4,
            )
            if any(item.duration_ms is not None for item in summaries)
            else None
        ),
        retrieved_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.retrieved_memory_ids
        ),
        selected_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.selected_memory_ids
        ),
        suppressed_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.suppressed_memory_ids
        ),
        conflict_resolutions=_unique_strings(
            item for summary in summaries for item in summary.conflict_resolutions
        ),
        lifecycle_events=_unique_strings(
            item for summary in summaries for item in summary.lifecycle_events
        ),
        explanations=_unique_strings(
            item for summary in summaries for item in summary.explanations
        ),
    )


def _build_summary(
    dataset: LOCOMODataset,
    metrics_by_system: Mapping[str, list[dict[str, float | int | None]]],
    trace_ids_by_system: Mapping[str, list[str]],
    judge_status_by_system: Mapping[str, list[str]],
    system_errors: Mapping[str, list[str]],
    mneno_available: bool,
    config: LOCOMOEvaluationConfig,
    validation_warnings: list[dict[str, object]],
    result_path: Path,
    report_path: Path,
    run: BenchmarkRun,
) -> dict[str, Any]:
    categories = Counter(
        _category_name(question.category)
        for conversation in dataset.conversations
        for question in conversation.questions
    )
    systems: dict[str, Any] = {}
    for system in SYSTEMS:
        errors = system_errors.get(system, [])
        if system == "mneno" and not mneno_available:
            status = RunStatus.SKIPPED
            skip_reason = INSTALL_MESSAGE
        elif errors and not metrics_by_system.get(system):
            status = RunStatus.FAILED
            skip_reason = None
        else:
            status = RunStatus.COMPLETED
            skip_reason = None
        systems[system] = {
            "status": status.value,
            "metrics": aggregate_metric_maps(metrics_by_system.get(system, [])),
            "score_labels": _score_labels(
                aggregate_metric_maps(metrics_by_system.get(system, []))
            ),
            "trace_ids": _unique_strings(trace_ids_by_system.get(system, [])),
            "judge": _judge_summary(config, judge_status_by_system.get(system, [])),
            "skip_reason": skip_reason,
            "errors": list(errors),
        }
    return {
        "dataset_status": "available",
        "execution_status": RunStatus.COMPLETED.value,
        "evaluation_mode": config.mode,
        "dataset_validation": {
            "strict": config.strict_dataset_validation,
            "allow_malformed_evidence": config.allow_malformed_evidence,
            "malformed_evidence_warning_count": len(validation_warnings),
            "warnings": validation_warnings,
        },
        "dataset": {
            "source_path": dataset.source_path,
            "benchmark_version": dataset.benchmark_version,
            "conversation_count": len(dataset.conversations),
            "message_count": dataset.message_count,
            "question_count": dataset.question_count,
            "categories": dict(sorted(categories.items())),
        },
        "systems": systems,
        "official_scoring": {
            "status": "unavailable",
            "reason": (
                "Official LOCOMO QA F1/category scoring is computed on local "
                "diagnostic answer candidates as locomo_official_f1_on_candidate; "
                "official_score remains null because generation is diagnostic."
                if config.mode == "deterministic_answer"
                else OFFICIAL_SCORING_PENDING
            ),
        },
        "judge_model": config.judge_model,
        "judge_provider": config.judge_provider,
        "prompt_version": config.prompt_version,
        "mneno_version": run.mneno_version,
        "result_path": str(result_path),
        "report_path": str(report_path),
        "trace_directory": str(result_path.parent / "traces"),
        "raw_output_directory": str(result_path.parent / "raw"),
        "judge_prompt_directory": str(result_path.parent / "judge" / "prompts"),
        "judge_response_directory": str(result_path.parent / "judge" / "responses"),
    }


def _benchmark_case(question: LOCOMOQuestion) -> BenchmarkCase:
    return BenchmarkCase(
        id=question.id,
        query=question.question,
        expected_memory_ids=question.evidence_ids,
        tags=[_category_name(question.category)],
        metadata={
            "benchmark": "locomo",
            "conversation_id": question.conversation_id,
            "category": question.category,
            "category_name": _category_name(question.category),
            "expected_answers": question.expected_answers,
            "official_scoring": "official_locomo_qa_f1_available_when_answer_exists",
            **question.metadata,
        },
    )


def _retrieval_metrics(
    retrieved_ids: list[str], question: LOCOMOQuestion
) -> dict[str, float | int | None]:
    return {
        "evidence_recall": evidence_recall(retrieved_ids, question.evidence_ids),
        "evidence_precision": evidence_precision(retrieved_ids, question.evidence_ids),
        "retrieval_hit_rate": retrieval_hit_rate(retrieved_ids, question.evidence_ids),
        "retrieved_dialog_count": len(retrieved_ids),
        "official_score": None,
        "diagnostic_score": None,
        "retrieval_diagnostic": evidence_recall(retrieved_ids, question.evidence_ids),
        "judge_score": None,
        "factual_recall": None,
        "temporal_reasoning": None,
        "multi_hop_reasoning": None,
        "multi_session_reasoning": None,
    }


def _metric_results(values: Mapping[str, float | int | None]) -> list[MetricResult]:
    placeholders = {metric.name: metric for metric in official_metric_placeholders()}
    results: list[MetricResult] = []
    for name, value in sorted(values.items()):
        if name in placeholders:
            results.append(placeholders[name].model_copy(update={"value": value}))
        else:
            results.append(
                MetricResult(
                    name=name,
                    value=float(value) if value is not None else None,
                    unit="count" if name.endswith("_count") else "ratio",
                    description=(
                        "Official evidence dialog IDs retrieved divided by "
                        "available official evidence IDs."
                        if name == "evidence_recall"
                        else _metric_description(name)
                    ),
                    unavailable_reason=(
                        "This question has no official evidence IDs."
                        if name == "evidence_recall" and value is None
                        else None
                    ),
                )
            )
    return results


def _normalized_result(
    provider: str,
    question: LOCOMOQuestion,
    metrics: dict[str, float | int | None],
    retrieved_ids: list[str] | None = None,
    trace_ids: list[str] | None = None,
    answer: AnswerCandidate | None = None,
    judge_result: JudgeResult | None = None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedLOCOMOResult:
    return NormalizedLOCOMOResult(
        provider=provider,
        metrics=metrics,
        official_score=_float_or_none(metrics.get("official_score")),
        diagnostic_score=_float_or_none(metrics.get("diagnostic_score")),
        retrieval_diagnostic=_float_or_none(metrics.get("retrieval_diagnostic")),
        judge_score=_float_or_none(metrics.get("judge_score")),
        trace_ids=trace_ids or [],
        metadata={
            "question_id": question.id,
            "conversation_id": question.conversation_id,
            "category": question.category,
            "expected_answers": question.expected_answers,
            "evidence_ids": question.evidence_ids,
            "retrieved_dialog_ids": retrieved_ids or [],
            "official_scoring": "separate_score_label",
            "answer_candidate": answer.model_dump(mode="json") if answer else None,
            "judge_result": judge_result.model_dump(mode="json")
            if judge_result
            else None,
            **(metadata or {}),
        },
    )


def _write_report(run: BenchmarkRun, path: Path) -> None:
    summary = run.export_metadata["locomo"]
    dataset = summary["dataset"]
    lines = [
        "# LOCOMO External Benchmark",
        "",
        f"- Run ID: `{run.run_id}`",
        f"- Status: **{run.status.value}**",
        f"- Dataset status: **{summary['dataset_status']}**",
        f"- Evaluation mode: **{summary.get('evaluation_mode', 'retrieval_only')}**",
        f"- Benchmark version: **{run.benchmark_version}**",
        f"- LOCOMO dataset version: **{dataset.get('benchmark_version', 'unavailable')}**",
        f"- Mneno version: **{run.mneno_version or 'not installed'}**",
        f"- Conversations: **{dataset['conversation_count']}**",
        f"- Messages: **{dataset['message_count']}**",
        f"- Questions: **{dataset['question_count']}**",
        "",
    ]
    if run.status == RunStatus.DATASET_MISSING:
        lines.extend(
            [
                "## Skipped",
                "",
                summary["skip_reason"],
                "",
                "Place the official dataset at `data/locomo/raw/locomo10.json`.",
            ]
        )
    else:
        lines.extend(
            [
                "## Execution Status",
                "",
                "| System | Status | Official Score | Diagnostic Score | Evidence Recall | Judge Score |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for system in SYSTEMS:
            item = summary["systems"][system]
            lines.append(
                f"| {system} | {item['status']} | "
                f"{_format_score(item['metrics'].get('official_score'))} | "
                f"{_format_score(item['metrics'].get('diagnostic_score'))} | "
                f"{_format_score(item['metrics'].get('evidence_recall'))} | "
                f"{_format_score(item['metrics'].get('judge_score'))} |"
            )
        lines.extend(
            [
                "",
                "## LOCOMO Metrics",
                "",
                "Retrieval diagnostics are always separated from answer quality. "
                "Deterministic answer candidates are local diagnostics. The "
                "official-compatible QA score reproduces the released LOCOMO "
                "category/F1 evaluator but must not be compared with leaderboard "
                "model scores unless the answer-generation setup also matches.",
                "",
                "Evidence recall is a retrieval diagnostic over official dialog "
                "evidence IDs; it is not an official LOCOMO answer score.",
                "",
                "## Judge",
                "",
                f"- Model: **{summary.get('judge_model') or 'not configured'}**",
                f"- Provider: **{summary.get('judge_provider') or 'not configured'}**",
                f"- Prompt version: **{summary.get('prompt_version')}**",
                f"- Prompts: `{summary['judge_prompt_directory']}`",
                f"- Responses: `{summary['judge_response_directory']}`",
                "",
                "## Dataset Validation",
                "",
                f"- Strict: **{summary['dataset_validation']['strict']}**",
                f"- Malformed evidence warnings: **{summary['dataset_validation']['malformed_evidence_warning_count']}**",
                "",
                "## Raw Outputs",
                "",
                f"- Mneno traces: `{summary['trace_directory']}`",
                f"- Mneno normalized/raw outputs: `{summary['raw_output_directory']}`",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_config(
    config_path: Path | None,
    k: int,
    evaluation_config: LOCOMOEvaluationConfig | None,
) -> LOCOMOEvaluationConfig:
    if evaluation_config is not None:
        return evaluation_config
    if config_path is not None:
        return LOCOMOEvaluationConfig.from_yaml(config_path)
    return LOCOMOEvaluationConfig()


def _build_judge(
    config: LOCOMOEvaluationConfig, results_dir: Path, run_id: str
) -> LOCOMOJudge | None:
    if config.mode != "llm_judge" or not config.judge_model:
        return None
    prompt_dir = results_dir / "locomo" / "judge" / "prompts" / run_id
    response_dir = results_dir / "locomo" / "judge" / "responses" / run_id
    if config.judge_config_path:
        client = LLMClient.from_yaml(
            config.judge_config_path,
            allow_external_calls=config.allow_external_calls,
        )
        return LOCOMOJudge(
            client,
            prompt_version=config.prompt_version,
            save_prompts=config.save_judge_prompts,
            prompt_dir=prompt_dir,
            response_dir=response_dir,
        )
    return LOCOMOJudge.from_config(
        config.judge_model,
        provider=config.judge_provider,
        allow_external_calls=config.allow_external_calls,
        prompt_version=config.prompt_version,
        save_prompts=config.save_judge_prompts,
        prompt_dir=prompt_dir,
        response_dir=response_dir,
    )


def _answer_for_mode(
    config: LOCOMOEvaluationConfig,
    provider: str,
    question: LOCOMOQuestion,
    context: str,
    trace_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AnswerCandidate | None:
    if config.mode == "retrieval_only":
        return None
    return generate_answer_from_context(
        provider,
        question.id,
        question.question,
        context,
        trace_ids=trace_ids,
        metadata=metadata,
    )


def _judge_for_mode(
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
    question: LOCOMOQuestion,
    answer: AnswerCandidate | None,
    results_dir: Path,
    run_id: str,
    provider: str,
) -> JudgeResult | None:
    if config.mode != "llm_judge" or answer is None:
        return None
    if judge is None:
        return JudgeResult(
            question_id=question.id,
            reason="Judge model/configuration is unavailable.",
            model=config.judge_model,
            provider=config.judge_provider,
            prompt_version=config.prompt_version,
            status="skipped",
        )
    provider_judge = LOCOMOJudge(
        judge.client,
        prompt_version=judge.prompt_version,
        save_prompts=judge.save_prompts,
        prompt_dir=(
            results_dir / "locomo" / "judge" / "prompts" / run_id / provider
            if judge.prompt_dir is not None
            else None
        ),
        response_dir=(
            results_dir / "locomo" / "judge" / "responses" / run_id / provider
            if judge.response_dir is not None
            else None
        ),
    )
    gold = question.expected_answers[0] if question.expected_answers else ""
    return provider_judge.evaluate(question.question, gold, answer)


def _apply_answer_metrics(
    values: dict[str, float | int | None],
    question: LOCOMOQuestion,
    answer: AnswerCandidate | None,
    judge_result: JudgeResult | None,
    config: LOCOMOEvaluationConfig,
) -> None:
    if answer is None:
        return
    gold = question.expected_answers[0] if question.expected_answers else ""
    values.update(
        {
            "exact_match": exact_match(answer.answer, gold),
            "normalized_exact_match": normalized_exact_match(answer.answer, gold),
            "token_f1": token_f1(answer.answer, gold),
            "contains_answer": contains_answer(answer.answer, gold),
            "diagnostic_score": answer_diagnostic_score(answer.answer, gold),
            "locomo_official_f1_on_candidate": official_locomo_qa_score(
                answer.answer, gold, question.category
            ),
        }
    )
    category_metric = _category_metric_name(question.category)
    if category_metric:
        values[category_metric] = values["locomo_official_f1_on_candidate"]
    # Answer generation is a local diagnostic, so the durable official_score stays null.
    values["official_score"] = None
    if config.mode == "llm_judge" and judge_result is not None:
        values["judge_score"] = judge_result.score


def _context_text(memories: list[dict[str, Any]], ids: list[str]) -> str:
    selected = set(ids)
    return "\n".join(
        str(memory.get("content", memory.get("text", "")))
        for memory in memories
        if str(memory["id"]) in selected
    )


def _validation_warnings(dataset: LOCOMODataset) -> list[dict[str, object]]:
    return locomo_validation_warnings(dataset)


def _score_labels(metrics: Mapping[str, float | None]) -> dict[str, float | None]:
    return {
        "official_score": metrics.get("official_score"),
        "diagnostic_score": metrics.get("diagnostic_score"),
        "retrieval_diagnostic": metrics.get("retrieval_diagnostic"),
        "judge_score": metrics.get("judge_score"),
    }


def _empty_score_labels() -> dict[str, None]:
    return {
        "official_score": None,
        "diagnostic_score": None,
        "retrieval_diagnostic": None,
        "judge_score": None,
    }


def _judge_summary(
    config: LOCOMOEvaluationConfig, statuses: list[str]
) -> dict[str, Any]:
    if config.mode != "llm_judge":
        return {"status": "not_requested", "model": None, "provider": None}
    if not statuses:
        status = "skipped"
    elif "completed" in statuses:
        status = "completed"
    elif "error" in statuses:
        status = "error"
    else:
        status = "skipped"
    return {
        "status": status,
        "model": config.judge_model,
        "provider": config.judge_provider,
        "prompt_version": config.prompt_version,
    }


def _category_metric_name(category: int | str) -> str | None:
    value = (
        int(category) if isinstance(category, int) or str(category).isdigit() else None
    )
    if value is None:
        return None
    return {
        1: "factual_recall",
        2: "temporal_reasoning",
        3: "multi_hop_reasoning",
        4: "multi_session_reasoning",
        5: "adversarial_answerability",
    }.get(value)


def _metric_description(name: str) -> str:
    return {
        "evidence_precision": "Relevant evidence dialogs divided by retrieved dialogs.",
        "retrieval_hit_rate": "Whether at least one official evidence dialog was retrieved.",
        "retrieved_dialog_count": "Number of dialog turns supplied by the system.",
        "official_score": "Reserved official score label; never inferred from diagnostics.",
        "diagnostic_score": "Local deterministic answer diagnostic.",
        "retrieval_diagnostic": "Evidence-recall retrieval diagnostic.",
        "judge_score": "Optional LiteLLM judge score.",
        "locomo_official_f1_on_candidate": "Released LOCOMO QA scorer applied to the local answer candidate.",
    }.get(name, "LOCOMO evaluation metric.")


def _float_or_none(value: float | int | None) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _format_score(value: Any) -> str:
    return "unavailable" if not isinstance(value, (int, float)) else f"{value:.4f}"


def _resolve_data_dir(data_dir: Path) -> Path:
    return data_dir / "locomo" if (data_dir / "locomo").is_dir() else data_dir


def _search_ids(result: NormalizedSearchResult) -> list[str]:
    return _extract_ids(result.raw_result)


def _extract_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in (
            "retrieved_memory_ids",
            "memory_ids",
            "included_memory_ids",
            "results",
            "memories",
            "ids",
        ):
            if key in value:
                return _extract_ids(value[key])
        item_id = value.get("id") or value.get("memory_id")
        return [str(item_id)] if item_id is not None else []
    if isinstance(value, list):
        ids: list[str] = []
        for item in value:
            if isinstance(item, str):
                ids.append(item)
            else:
                ids.extend(_extract_ids(item))
        return ids
    return []


def _normalize_ids(values: list[str], reverse_id_map: Mapping[str, str]) -> list[str]:
    return _unique_strings(reverse_id_map.get(value, value) for value in values)


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        item = str(value)
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _context_tokens(memories: list[dict[str, Any]], retrieved_ids: list[str]) -> int:
    selected = set(retrieved_ids)
    return sum(
        estimate_tokens(str(memory.get("content", memory.get("text", ""))))
        for memory in memories
        if str(memory["id"]) in selected
    )


def _category_name(category: int | str) -> str:
    if isinstance(category, int):
        return CATEGORY_NAMES.get(category, f"category_{category}")
    return str(category).strip().lower().replace(" ", "_")


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "item"


@app.command()
def main(
    data_dir: Path = typer.Option(PROJECT_ROOT / "data", exists=True),
    results_dir: Path = typer.Option(PROJECT_ROOT / "results"),
    k: int = typer.Option(5, min=1),
    config: Path | None = typer.Option(None),
    mode: LOCOMOEvaluationMode = typer.Option("retrieval_only"),
    judge_model: str | None = typer.Option(None),
    judge_provider: str | None = typer.Option(None),
    max_cases: int | None = typer.Option(None, min=1),
    allow_external_calls: bool = typer.Option(False),
    allow_malformed_evidence: bool = typer.Option(False),
) -> None:
    """Run LOCOMO against local baselines and an optional Mneno installation."""

    evaluation_config = (
        None
        if config is not None
        else LOCOMOEvaluationConfig(
            mode=mode,
            judge_model=judge_model,
            judge_provider=judge_provider,
            max_cases=max_cases,
            strict_dataset_validation=not allow_malformed_evidence,
            allow_malformed_evidence=allow_malformed_evidence,
            allow_external_calls=allow_external_calls,
        )
    )
    run_locomo(
        data_dir,
        results_dir,
        k=k,
        config_path=config,
        evaluation_config=evaluation_config,
    )


if __name__ == "__main__":
    app()
