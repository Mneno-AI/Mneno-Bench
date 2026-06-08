"""Deterministic metrics for Mneno Context Rot Suite v1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from benchmarks.common.schema import MnenoDecisionSummary, TraceSummary
from benchmarks.common.utils import estimate_tokens
from benchmarks.mneno_suite.dataset import MnenoSuiteMemory

INACTIVE_STATUSES = {"archived", "expired", "rejected", "stale", "superseded"}


def stale_memory_suppression_rate(
    retrieved_ids: Sequence[str], forbidden_ids: Sequence[str]
) -> float:
    forbidden = set(forbidden_ids)
    if not forbidden:
        return 1.0
    return _ratio(len(forbidden - set(retrieved_ids)), len(forbidden))


def expected_memory_recall(
    retrieved_ids: Sequence[str], expected_ids: Sequence[str]
) -> float:
    expected = set(expected_ids)
    if not expected:
        return 1.0
    return _ratio(len(set(retrieved_ids) & expected), len(expected))


def forbidden_memory_error_rate(
    retrieved_ids: Sequence[str], forbidden_ids: Sequence[str]
) -> float:
    forbidden = set(forbidden_ids)
    if not forbidden:
        return 0.0
    return _ratio(len(set(retrieved_ids) & forbidden), len(forbidden))


def context_efficiency_score(
    retrieved_ids: Sequence[str],
    expected_ids: Sequence[str],
    memories: Mapping[str, MnenoSuiteMemory],
) -> float:
    retrieved = set(retrieved_ids)
    expected = set(expected_ids)
    supplied_tokens = sum(
        estimate_tokens(memories[memory_id].content)
        for memory_id in retrieved
        if memory_id in memories
    )
    useful_tokens = sum(
        estimate_tokens(memories[memory_id].content)
        for memory_id in retrieved & expected
        if memory_id in memories
    )
    return _ratio(useful_tokens, supplied_tokens)


def lifecycle_alignment_score(
    retrieved_ids: Sequence[str],
    expected_ids: Sequence[str],
    forbidden_ids: Sequence[str],
    memories: Mapping[str, MnenoSuiteMemory],
) -> float:
    active_expected = {
        memory_id
        for memory_id in expected_ids
        if memory_id in memories
        and (memories[memory_id].status or "active") not in INACTIVE_STATUSES
    }
    inactive_forbidden = {
        memory_id
        for memory_id in forbidden_ids
        if memory_id in memories
        and (memories[memory_id].status or "active") in INACTIVE_STATUSES
    }
    retrieved = set(retrieved_ids)
    aligned = len(active_expected & retrieved) + len(inactive_forbidden - retrieved)
    total = len(active_expected) + len(inactive_forbidden)
    return _ratio(aligned, total) if total else 1.0


def session_continuity_score(
    retrieved_ids: Sequence[str],
    expected_ids: Sequence[str],
    forbidden_ids: Sequence[str],
    memories: Mapping[str, MnenoSuiteMemory],
    current_session_id: str | None,
) -> float:
    if current_session_id is None:
        return 1.0
    expected_current = {
        memory_id
        for memory_id in expected_ids
        if memory_id in memories
        and memories[memory_id].session_id == current_session_id
    }
    forbidden_other = {
        memory_id
        for memory_id in forbidden_ids
        if memory_id in memories
        and memories[memory_id].session_id != current_session_id
    }
    retrieved = set(retrieved_ids)
    aligned = len(expected_current & retrieved) + len(forbidden_other - retrieved)
    total = len(expected_current) + len(forbidden_other)
    return _ratio(aligned, total) if total else 1.0


def compaction_retention_score(
    compacted_ids: Sequence[str],
    expected_ids: Sequence[str],
    memories: Mapping[str, MnenoSuiteMemory],
    minimum_importance: float = 0.8,
) -> float:
    important = {
        memory_id
        for memory_id in expected_ids
        if memory_id in memories
        and memories[memory_id].importance >= minimum_importance
    }
    if not important:
        return 1.0
    return _ratio(len(set(compacted_ids) & important), len(important))


def explainability_coverage_score(
    retrieved_ids: Sequence[str],
    trace_summary: TraceSummary | None,
    decision_summary: MnenoDecisionSummary | None = None,
) -> float:
    if trace_summary is None and decision_summary is None:
        return 0.0
    evidence_count = 0
    if trace_summary is not None:
        evidence_count += (
            len(trace_summary.explanations)
            + trace_summary.decision_count
            + trace_summary.event_count
        )
    if decision_summary is not None:
        evidence_count += sum(
            len(reasons) for reasons in decision_summary.inclusion_reasons.values()
        )
        evidence_count += sum(
            len(reasons) for reasons in decision_summary.exclusion_reasons.values()
        )
        evidence_count += len(decision_summary.conflict_events)
        evidence_count += len(decision_summary.hierarchy_events)
        evidence_count += len(decision_summary.session_events)
    return min(_ratio(evidence_count, max(len(set(retrieved_ids)), 1)), 1.0)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(min(max(numerator / denominator, 0.0), 1.0), 6)
