from benchmarks.common.failures import FailureCategory
from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRun,
    RunStatus,
)
from benchmarks.locomo.failure_analysis import analyze_locomo_failures


def _run(result: BenchmarkResult, warnings: list[dict[str, object]] | None = None):
    return BenchmarkRun(
        run_id="locomo-run",
        suite="locomo",
        status=RunStatus.COMPLETED,
        started_at="2026-06-09T00:00:00Z",
        finished_at="2026-06-09T00:01:00Z",
        systems=["keyword_baseline"],
        results=[result],
        export_metadata={
            "locomo": {
                "dataset_status": "available",
                "evaluation_mode": "deterministic_answer",
                "dataset_validation": {"warnings": warnings or []},
            }
        },
    )


def test_locomo_failure_analysis_uses_dataset_warning() -> None:
    result = BenchmarkResult(
        case=BenchmarkCase(
            id="q1",
            query="Where?",
            expected_memory_ids=["missing-dialog"],
            metadata={"category": 1, "category_name": "factual_recall"},
        ),
        baseline_results=[BaselineResult(name="keyword_baseline")],
    )
    warning = {
        "type": "missing_evidence_reference",
        "question_id": "q1",
        "missing_evidence_ids": ["missing-dialog"],
    }

    report = analyze_locomo_failures(_run(result, [warning]))

    assert FailureCategory.DATASET_ISSUE in {
        failure.category for failure in report.failures
    }


def test_locomo_failure_analysis_detects_answer_metric_failure() -> None:
    result = BenchmarkResult(
        case=BenchmarkCase(
            id="q2",
            query="Where?",
            expected_memory_ids=["D1:1"],
            metadata={"category": 1, "category_name": "factual_recall"},
        ),
        baseline_results=[
            BaselineResult(
                name="keyword_baseline",
                retrieved_memory_ids=["D1:1"],
                metadata={
                    "locomo_result": {
                        "metrics": {"diagnostic_score": 0.0},
                        "metadata": {},
                    }
                },
            )
        ],
    )

    report = analyze_locomo_failures(_run(result))

    assert {failure.category for failure in report.failures} == {
        FailureCategory.ANSWER_GENERATION_FAILURE
    }


def test_locomo_failure_analysis_flags_missing_required_evidence() -> None:
    result = BenchmarkResult(
        case=BenchmarkCase(
            id="q3",
            query="Who?",
            metadata={"category": 1, "category_name": "factual_recall"},
        ),
        baseline_results=[BaselineResult(name="keyword_baseline")],
    )

    report = analyze_locomo_failures(_run(result))

    assert {failure.category for failure in report.failures} == {
        FailureCategory.DATASET_ISSUE
    }
