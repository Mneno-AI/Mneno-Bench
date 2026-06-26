from typing import Any

import pytest

from benchmarks.common.failures import FailureCategory
from benchmarks.common.root_cause import (
    FailureClassifier,
    analyze_trace_for_failure_signals,
)


def _classify(**overrides: Any):
    values = {
        "benchmark": "suite",
        "case_id": "case-1",
        "provider": "mneno",
        "query": "What should be remembered?",
        "expected_ids": ["expected"],
        "forbidden_ids": [],
        "retrieved_ids": ["expected"],
        "included_ids": ["expected"],
        "excluded_ids": [],
        "trace_ids": [],
        "trace_summaries": None,
        "metadata": None,
    }
    values.update(overrides)
    return FailureClassifier().classify_case(**values)


def _categories(failures: list[Any]) -> set[FailureCategory]:
    return {failure.category for failure in failures}


def test_classifies_retrieval_failure() -> None:
    failures = _classify(retrieved_ids=[], included_ids=[])
    assert _categories(failures) == {FailureCategory.RETRIEVAL_FAILURE}


def test_classifies_ranking_failure() -> None:
    failures = _classify(
        included_ids=[], excluded_ids=["expected"], metadata={"context_available": True}
    )
    assert _categories(failures) == {FailureCategory.RANKING_FAILURE}


def test_classifies_low_rank_failure_from_metadata() -> None:
    failures = _classify(
        metadata={"retrieval_ranks": {"expected": 8}, "rank_cutoff": 5}
    )
    assert FailureCategory.RANKING_FAILURE in _categories(failures)


def test_classifies_context_budget_failure() -> None:
    failures = _classify(
        included_ids=[],
        excluded_ids=["expected"],
        trace_summaries=[
            {
                "events": [
                    {
                        "event_type": "memory_excluded",
                        "data": {
                            "memory_id": "expected",
                            "reason_code": "budget_exhausted",
                        },
                    }
                ]
            }
        ],
        metadata={"context_available": True},
    )
    assert FailureCategory.CONTEXT_BUDGET_FAILURE in _categories(failures)


def test_classifies_lifecycle_filter_failure() -> None:
    failures = _classify(
        included_ids=[],
        excluded_ids=["expected"],
        trace_summaries=[
            {
                "events": [
                    {
                        "event_type": "memory_excluded",
                        "data": {
                            "memory_id": "expected",
                            "lifecycle_status": "archived",
                            "decision": "filtered",
                        },
                    }
                ]
            }
        ],
        metadata={"context_available": True},
    )
    assert FailureCategory.LIFECYCLE_FILTER_FAILURE in _categories(failures)


def test_classifies_session_continuity_failure() -> None:
    failures = _classify(
        retrieved_ids=[],
        included_ids=[],
        metadata={
            "current_session_id": "session-2",
            "memory_sessions": {"expected": "session-2"},
        },
    )
    assert FailureCategory.SESSION_CONTINUITY_FAILURE in _categories(failures)


def test_classifies_conflict_resolution_failure() -> None:
    failures = _classify(
        forbidden_ids=["stale"],
        retrieved_ids=["expected", "stale"],
        included_ids=["expected", "stale"],
    )
    assert _categories(failures) == {FailureCategory.CONFLICT_RESOLUTION_FAILURE}


def test_classifies_compaction_failure() -> None:
    failures = _classify(metadata={"compacted_ids": []})
    assert _categories(failures) == {FailureCategory.COMPACTION_FAILURE}


def test_classifies_answer_generation_failure() -> None:
    failures = _classify(metadata={"answer_metrics": {"diagnostic_score": 0.0}})
    assert _categories(failures) == {FailureCategory.ANSWER_GENERATION_FAILURE}


@pytest.mark.parametrize("status", ["error", "invalid", "skipped"])
def test_classifies_judge_failure(status: str) -> None:
    failures = _classify(
        metadata={
            "judge_requested": True,
            "judge_result": {"status": status, "reason": "bad output"},
        }
    )
    assert _categories(failures) == {FailureCategory.JUDGE_FAILURE}


def test_classifies_dataset_issue() -> None:
    failures = _classify(
        expected_ids=[],
        retrieved_ids=[],
        included_ids=[],
        metadata={"evidence_required": True},
    )
    assert _categories(failures) == {FailureCategory.DATASET_ISSUE}


def test_unknown_is_used_only_for_explicit_unexplained_failure() -> None:
    failures = _classify(metadata={"failure_observed": True})
    assert _categories(failures) == {FailureCategory.UNKNOWN}


def test_successful_case_has_no_failure() -> None:
    assert _classify() == []


def test_multiple_failure_categories_can_apply() -> None:
    failures = _classify(
        forbidden_ids=["stale"],
        retrieved_ids=["expected", "stale"],
        included_ids=["stale"],
        excluded_ids=["expected"],
        trace_summaries=[
            {
                "events": [
                    {
                        "event_type": "memory_excluded",
                        "data": {
                            "memory_id": "expected",
                            "reason_code": "budget_exhausted",
                        },
                    }
                ]
            }
        ],
        metadata={"context_available": True},
    )
    assert {
        FailureCategory.RANKING_FAILURE,
        FailureCategory.CONTEXT_BUDGET_FAILURE,
        FailureCategory.CONFLICT_RESOLUTION_FAILURE,
    } <= _categories(failures)


def test_provider_specific_actions_and_expected_baseline_behavior() -> None:
    baseline = _classify(
        provider="full_context_baseline",
        forbidden_ids=["stale"],
        retrieved_ids=["expected", "stale"],
        included_ids=["expected", "stale"],
    )[0]
    mneno = _classify(retrieved_ids=[], included_ids=[])[0]

    assert baseline.category == FailureCategory.CONFLICT_RESOLUTION_FAILURE
    assert baseline.expected_behavior
    assert baseline.suggested_action.startswith("Comparison evidence:")
    assert baseline.interpretation is not None
    assert "intentionally includes all memories" in baseline.interpretation
    assert mneno.suggested_action.startswith("Mneno Core:")


def test_trace_analysis_detects_budget_and_exclusion() -> None:
    signals = analyze_trace_for_failure_signals(
        {
            "trace": {
                "events": [
                    {
                        "event_type": "memory_excluded",
                        "data": {
                            "memory_id": "m1",
                            "reason_code": "budget_exhausted",
                        },
                    }
                ]
            }
        }
    )
    assert signals["budget_exhausted"]
    assert signals["excluded_memory_ids"] == ["m1"]
    assert signals["budget_excluded_ids"] == ["m1"]


def test_trace_analysis_detects_lifecycle_exclusion() -> None:
    signals = analyze_trace_for_failure_signals(
        {
            "events": [
                {
                    "event_type": "memory_filtered",
                    "data": {
                        "memory_id": "m2",
                        "status": "superseded",
                        "decision": "exclude",
                    },
                }
            ]
        }
    )
    assert signals["archived_or_superseded_filtering"]
    assert signals["lifecycle_excluded_ids"] == ["m2"]


def test_trace_analysis_detects_conflict_event() -> None:
    signals = analyze_trace_for_failure_signals(
        {"events": [{"event_type": "conflict_resolved", "data": {}}]}
    )
    assert signals["conflict_event"]


def test_trace_analysis_handles_unknown_structure() -> None:
    signals = analyze_trace_for_failure_signals({"unexpected": {"shape": 1}})
    assert not any(value for value in signals.values())
