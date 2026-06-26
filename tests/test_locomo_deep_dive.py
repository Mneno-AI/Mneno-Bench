from pathlib import Path

from benchmarks.common.failures import (
    FailureCase,
    FailureCategory,
    FailureReport,
    FailureSeverity,
    RootCauseSummary,
)
from benchmarks.locomo.deep_dive import (
    ContextMemory,
    ContextPackageEvidence,
    EvidenceMemory,
    RetrievalFailureAnalysis,
    RetrievalFailureInspection,
    RetrievalRootCause,
    RetrievedCandidate,
    TraceEventEvidence,
    TraceInspection,
    aggregate_retrieval_statistics,
    classify_retrieval_root_cause,
    sample_retrieval_failures,
    write_retrieval_deep_dive,
)


def _failure(index: int, conversation: str, category: str) -> FailureCase:
    return FailureCase(
        id=f"failure-{index}",
        benchmark="locomo",
        case_id=f"{conversation}:qa-{index:04d}",
        provider="mneno",
        category=FailureCategory.RETRIEVAL_FAILURE,
        severity=FailureSeverity.HIGH,
        query=f"Question {index}?",
        expected_ids=[f"D{index}:1"],
        reason="Expected evidence was absent.",
        suggested_action="Inspect retrieval.",
        metadata={
            "conversation_id": conversation,
            "benchmark_category": category,
        },
    )


def _report(failures: list[FailureCase]) -> FailureReport:
    return FailureReport(
        id="locomo-failures",
        benchmark="locomo",
        run_id="run-1",
        created_at="2026-06-09T00:00:00Z",
        failures=failures,
        summary=RootCauseSummary.from_failures(failures),
    )


def _inspection(
    cause: RetrievalRootCause = RetrievalRootCause.UNKNOWN,
) -> RetrievalFailureInspection:
    return RetrievalFailureInspection(
        id="failure-1",
        case_id="conv-1:qa-0001",
        provider="mneno",
        conversation_id="conv-1",
        question_type="factual_recall",
        category="factual_recall",
        sessions=["session_1"],
        question="Where was it?",
        normalized_question="where was it",
        expected_evidence=[
            EvidenceMemory(
                evidence_id="D1:1",
                text="The expected fact.",
                core_memory_id="core-expected",
                session_id="session_1",
            )
        ],
        retrieved_candidates=[
            RetrievedCandidate(
                id="D1:1",
                core_memory_id="core-expected",
                text="The expected fact.",
                score=0.5,
                relevance=0.5,
            ),
            RetrievedCandidate(
                id="D2:1",
                core_memory_id="core-selected",
                text="Another fact.",
                score=0.7,
                selected=True,
                rank=1,
            ),
        ],
        context_package=ContextPackageEvidence(
            included_memories=[
                ContextMemory(
                    id="D2:1",
                    core_memory_id="core-selected",
                    text="Another fact.",
                )
            ],
            excluded_memories=[
                ContextMemory(
                    id="D1:1",
                    core_memory_id="core-expected",
                    text="The expected fact.",
                    reason="Excluded because not selected by policy",
                )
            ],
        ),
        trace=TraceInspection(trace_ids=["trace-1"]),
        root_cause=cause,
    )


def test_sampling_balances_conversations_categories_and_sessions() -> None:
    failures = [
        _failure(index, f"conv-{index % 4}", ["factual", "temporal"][index % 2])
        for index in range(24)
    ]
    sessions = {
        failure.case_id: [f"session_{index % 3}"]
        for index, failure in enumerate(failures)
    }

    first = sample_retrieval_failures(
        _report(failures), 8, 17, sessions_by_case=sessions
    )
    second = sample_retrieval_failures(
        _report(failures), 8, 17, sessions_by_case=sessions
    )

    assert [item.id for item in first] == [item.id for item in second]
    assert len({item.metadata["conversation_id"] for item in first}) == 4
    assert len({item.metadata["benchmark_category"] for item in first}) == 2
    assert len({sessions[item.case_id][0] for item in first}) == 3


def test_root_cause_classification_requires_observable_evidence() -> None:
    ranking = classify_retrieval_root_cause(_inspection())
    assert ranking.root_cause == RetrievalRootCause.RANKING_FAILURE

    unknown = _inspection().model_copy(
        update={
            "expected_evidence": [
                EvidenceMemory(evidence_id="D1:1", text="The expected fact.")
            ],
            "retrieved_candidates": [],
        }
    )
    classified_unknown = classify_retrieval_root_cause(unknown)
    assert classified_unknown.root_cause == RetrievalRootCause.UNKNOWN


def test_root_cause_classification_detects_authoritative_budget_exclusion() -> None:
    inspection = _inspection().model_copy(
        update={
            "trace": TraceInspection(
                trace_ids=["trace-context"],
                budget_events=[
                    TraceEventEvidence(
                        trace_id="trace-context",
                        event_type="budget_exhausted",
                        memory_id="core-expected",
                        evidence_id="D1:1",
                        message="Excluded because budget exhausted",
                    )
                ],
            ),
            "metadata": {
                "authoritative_selection_trace_ids": ["trace-context"]
            },
        }
    )

    classification = classify_retrieval_root_cause(inspection)
    assert classification.root_cause == RetrievalRootCause.BUDGET_EXCLUSION


def test_statistics_aggregate_counts_percentages_and_coverage() -> None:
    ranking = _inspection(RetrievalRootCause.RANKING_FAILURE)
    selected = _inspection(RetrievalRootCause.UNKNOWN).model_copy(
        update={
            "id": "failure-2",
            "case_id": "conv-2:qa-0002",
            "conversation_id": "conv-2",
            "retrieved_candidates": [
                RetrievedCandidate(
                    id="D1:1",
                    core_memory_id="core-expected",
                    selected=True,
                )
            ],
        }
    )

    statistics = aggregate_retrieval_statistics([ranking, selected])

    assert statistics.retrieval_recall == 0.5
    assert statistics.candidate_coverage == 1.0
    assert statistics.failures_by_root_cause["ranking_failure"].percentage == 50.0
    assert statistics.failures_by_conversation["conv-1"].count == 1


def test_report_generation_writes_json_markdown_and_dashboard_projection(
    tmp_path: Path,
) -> None:
    inspection = _inspection(RetrievalRootCause.RANKING_FAILURE)
    statistics = aggregate_retrieval_statistics([inspection])
    analysis = RetrievalFailureAnalysis(
        benchmark="locomo",
        created_at="2026-06-09T00:00:00Z",
        provider="mneno",
        total_failures=1,
        sampled_failures=[inspection],
        root_causes=statistics.failures_by_root_cause,
        statistics=statistics,
        top_failure_cases=[inspection],
        recommended_core_priorities=["Candidate ranking"],
        run_id="run-1",
    )

    json_path, markdown_path, dashboard_path = write_retrieval_deep_dive(
        analysis, tmp_path
    )

    assert json_path.is_file()
    assert dashboard_path.is_file()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Retrieval Deep Dive" in markdown
    assert "## Top Root Causes" in markdown
    assert "## Top Failure Cases" in markdown
    assert "## Improvement Opportunities" in markdown
    assert "## Recommended Core Priorities" in markdown
