from benchmarks.common.failures import FailureCategory
from benchmarks.common.failures import failure_report_summary
from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRun,
    MnenoDecisionSummary,
    MnenoResult,
    RunStatus,
)
from benchmarks.mneno_suite.failure_analysis import (
    analyze_mneno_suite_failures,
)


def test_mneno_suite_failure_analysis_computes_top_categories() -> None:
    run = BenchmarkRun(
        run_id="context-run",
        suite="mneno_context_rot_suite_v1",
        status=RunStatus.COMPLETED,
        started_at="2026-06-09T00:00:00Z",
        finished_at="2026-06-09T00:01:00Z",
        systems=["keyword_baseline", "mneno"],
        results=[
            BenchmarkResult(
                case=BenchmarkCase(
                    id="budget-case",
                    query="Keep the important fact.",
                    expected_memory_ids=["expected"],
                    metadata={
                        "category": "context_budget",
                        "forbidden_memory_ids": [],
                    },
                ),
                baseline_results=[
                    BaselineResult(
                        name="keyword_baseline",
                        retrieved_memory_ids=["expected"],
                    )
                ],
                mneno_result=MnenoResult(
                    status=RunStatus.COMPLETED,
                    retrieved_memory_ids=["expected"],
                    excluded_memory_ids=["expected"],
                    trace_ids=["trace-1"],
                    decision_summary=MnenoDecisionSummary(
                        retrieved_ids=["expected"],
                        excluded_ids=["expected"],
                        trace_ids=["trace-1"],
                        exclusion_reasons={"expected": ["budget_exhausted"]},
                    ),
                ),
            )
        ],
    )

    report = analyze_mneno_suite_failures(run)
    summary = failure_report_summary(report)

    categories = {failure.category for failure in report.failures}
    assert FailureCategory.CONTEXT_BUDGET_FAILURE in categories
    assert summary["failure_count"] == len(report.failures)
    assert summary["top_categories"]["context_budget_failure"] == 1
