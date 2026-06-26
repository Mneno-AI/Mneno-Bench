"""Failure analysis for Mneno Context Rot Suite benchmark runs."""

from __future__ import annotations

from typing import Any

from benchmarks.common.failures import FailureReport, RootCauseSummary
from benchmarks.common.root_cause import FailureClassifier
from benchmarks.common.schema import BenchmarkRun, MnenoResult


def analyze_mneno_suite_failures(run_result: BenchmarkRun) -> FailureReport:
    classifier = FailureClassifier()
    failures = []
    for result in run_result.results:
        case = result.case
        forbidden_ids = case.stale_memory_ids or _strings(
            case.metadata.get("forbidden_memory_ids")
        )
        for baseline in result.baseline_results:
            failures.extend(
                classifier.classify_case(
                    benchmark="mneno_context_rot_suite_v1",
                    case_id=case.id,
                    provider=baseline.name,
                    query=case.query,
                    expected_ids=case.expected_memory_ids,
                    forbidden_ids=forbidden_ids,
                    retrieved_ids=baseline.retrieved_memory_ids,
                    included_ids=baseline.retrieved_memory_ids,
                    excluded_ids=[],
                    trace_ids=[],
                    metadata={
                        **case.metadata,
                        "benchmark_category": case.metadata.get("category"),
                        "status": baseline.status.value,
                        "context_available": False,
                        "failure_observed": bool(baseline.error),
                    },
                )
            )
        if result.mneno_result is not None:
            mneno = result.mneno_result
            failures.extend(
                classifier.classify_case(
                    benchmark="mneno_context_rot_suite_v1",
                    case_id=case.id,
                    provider="mneno",
                    query=case.query,
                    expected_ids=case.expected_memory_ids,
                    forbidden_ids=forbidden_ids,
                    retrieved_ids=mneno.retrieved_memory_ids,
                    included_ids=mneno.included_memory_ids,
                    excluded_ids=mneno.excluded_memory_ids,
                    trace_ids=mneno.trace_ids,
                    trace_summaries=_trace_inputs(mneno),
                    metadata={
                        **case.metadata,
                        "benchmark_category": case.metadata.get("category"),
                        "status": mneno.status.value,
                        "skip_reason": mneno.skip_reason,
                        "context_available": bool(
                            mneno.included_memory_ids or mneno.excluded_memory_ids
                        ),
                        "failure_observed": bool(mneno.error),
                        "compacted_ids": mneno.metadata.get("compacted_memory_ids"),
                        "compaction_available": mneno.metadata.get(
                            "compacted_memory_ids"
                        )
                        is not None,
                    },
                )
            )
    summary = RootCauseSummary.from_failures(failures)
    return FailureReport(
        id=f"{run_result.run_id}-failures",
        benchmark="mneno_context_rot_suite_v1",
        run_id=run_result.run_id,
        created_at=run_result.finished_at or run_result.started_at,
        failures=failures,
        summary=summary,
        metadata={
            "format": "mneno-bench.failure-report",
            "version": 1,
            "suite": run_result.suite,
            "benchmark_version": run_result.benchmark_version,
            "deterministic": True,
        },
    )


def _trace_inputs(result: MnenoResult) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    if result.trace_summary is not None:
        traces.append(result.trace_summary.model_dump(mode="json"))
    decision = result.decision_summary
    if decision is None:
        return traces
    events: list[dict[str, Any]] = []
    for memory_id, reasons in decision.exclusion_reasons.items():
        events.extend(
            {
                "event_type": "memory_excluded",
                "data": {"memory_id": memory_id, "reason": reason},
            }
            for reason in reasons
        )
    events.extend(decision.conflict_events)
    events.extend(decision.hierarchy_events)
    events.extend(decision.session_events)
    traces.append({"events": events})
    return traces


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []
