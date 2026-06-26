"""Failure analysis for normalized LOCOMO benchmark runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from benchmarks.common.failures import (
    FailureCase,
    FailureCategory,
    FailureReport,
    FailureSeverity,
    RootCauseSummary,
    failure_report_summary,
)
from benchmarks.common.root_cause import ACTION_BY_CATEGORY, FailureClassifier
from benchmarks.common.schema import BenchmarkResult, BenchmarkRun


def analyze_locomo_failures(run_result: BenchmarkRun) -> FailureReport:
    summary = _mapping(run_result.export_metadata.get("locomo"))
    if summary.get("dataset_status") == "dataset_missing":
        failures = [_missing_dataset_failure(run_result, summary)]
    else:
        failures = []
        warnings = _warnings_by_case(summary)
        evaluation_mode = str(summary.get("evaluation_mode", "retrieval_only"))
        classifier = FailureClassifier()
        for result in run_result.results:
            failures.extend(
                _analyze_result(result, classifier, warnings, evaluation_mode)
            )
    root_causes = RootCauseSummary.from_failures(failures)
    return FailureReport(
        id=f"{run_result.run_id}-failures",
        benchmark="locomo",
        run_id=run_result.run_id,
        created_at=run_result.finished_at or run_result.started_at,
        failures=failures,
        summary=root_causes,
        metadata={
            "format": "mneno-bench.failure-report",
            "version": 1,
            "suite": run_result.suite,
            "benchmark_version": run_result.benchmark_version,
            "evaluation_mode": summary.get("evaluation_mode", "retrieval_only"),
            "deterministic": True,
        },
    )


def locomo_failure_report_summary(report: FailureReport) -> dict[str, Any]:
    return failure_report_summary(report)


def _analyze_result(
    result: BenchmarkResult,
    classifier: FailureClassifier,
    warnings: dict[str, list[dict[str, Any]]],
    evaluation_mode: str,
) -> list[FailureCase]:
    case = result.case
    base_metadata = {
        **case.metadata,
        "benchmark_category": case.metadata.get("category_name"),
        "conversation_id": case.metadata.get("conversation_id"),
        "evaluation_mode": evaluation_mode,
        "dataset_warnings": warnings.get(case.id, []),
        "evidence_required": str(case.metadata.get("category")) != "5",
        "judge_requested": evaluation_mode == "llm_judge",
    }
    failures: list[FailureCase] = []
    for baseline in result.baseline_results:
        normalized = _mapping(baseline.metadata.get("locomo_result"))
        result_metadata = _mapping(normalized.get("metadata"))
        failures.extend(
            classifier.classify_case(
                benchmark="locomo",
                case_id=case.id,
                provider=baseline.name,
                query=case.query,
                expected_ids=case.expected_memory_ids,
                forbidden_ids=[],
                retrieved_ids=baseline.retrieved_memory_ids,
                included_ids=baseline.retrieved_memory_ids,
                excluded_ids=[],
                trace_ids=_strings(normalized.get("trace_ids")),
                metadata={
                    **base_metadata,
                    "status": baseline.status.value,
                    "context_available": False,
                    "failure_observed": bool(baseline.error),
                    "answer_metrics": _mapping(normalized.get("metrics")),
                    "judge_result": _mapping(result_metadata.get("judge_result")),
                },
            )
        )
    mneno = result.mneno_result
    if mneno is not None:
        normalized = _mapping(mneno.metadata.get("locomo_result"))
        result_metadata = _mapping(normalized.get("metadata"))
        failures.extend(
            classifier.classify_case(
                benchmark="locomo",
                case_id=case.id,
                provider="mneno",
                query=case.query,
                expected_ids=case.expected_memory_ids,
                forbidden_ids=[],
                retrieved_ids=mneno.retrieved_memory_ids,
                included_ids=mneno.included_memory_ids,
                excluded_ids=mneno.excluded_memory_ids,
                trace_ids=mneno.trace_ids,
                trace_summaries=(
                    [mneno.trace_summary.model_dump(mode="json")]
                    if mneno.trace_summary is not None
                    else None
                ),
                metadata={
                    **base_metadata,
                    "status": mneno.status.value,
                    "skip_reason": mneno.skip_reason,
                    "context_available": bool(
                        mneno.included_memory_ids or mneno.excluded_memory_ids
                    ),
                    "failure_observed": bool(mneno.error),
                    "answer_metrics": _mapping(normalized.get("metrics")),
                    "judge_result": _mapping(result_metadata.get("judge_result")),
                },
            )
        )
    return failures


def _missing_dataset_failure(
    run_result: BenchmarkRun, summary: Mapping[str, Any]
) -> FailureCase:
    reason = str(summary.get("skip_reason") or "LOCOMO dataset is unavailable.")
    return FailureCase(
        id="locomo:dataset:dataset:dataset_issue",
        benchmark="locomo",
        case_id="dataset",
        provider="dataset",
        category=FailureCategory.DATASET_ISSUE,
        severity=FailureSeverity.CRITICAL,
        query="",
        reason=reason,
        evidence=["dataset_status=dataset_missing"],
        suggested_action=ACTION_BY_CATEGORY[FailureCategory.DATASET_ISSUE],
        metadata={"run_id": run_result.run_id},
    )


def _warnings_by_case(summary: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    validation = _mapping(summary.get("dataset_validation"))
    output: dict[str, list[dict[str, Any]]] = {}
    for warning in _list_of_mappings(validation.get("warnings")):
        case_id = warning.get("question_id")
        if case_id is not None:
            output.setdefault(str(case_id), []).append(warning)
    return output


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    return [_mapping(item) for item in value] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []
