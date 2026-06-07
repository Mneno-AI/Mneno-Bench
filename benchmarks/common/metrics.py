"""Deterministic retrieval and context-efficiency metrics."""

from __future__ import annotations


def precision_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    relevant = set(relevant_ids)
    return sum(item in relevant for item in top_k) / k


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    return len(set(retrieved_ids[: max(k, 0)]) & relevant) / len(relevant)


def mean_reciprocal_rank(
    ranked_results: list[list[str]], relevant_results: list[list[str]]
) -> float:
    if not ranked_results:
        return 0.0
    reciprocal_ranks: list[float] = []
    for retrieved, relevant_ids in zip(ranked_results, relevant_results, strict=False):
        relevant = set(relevant_ids)
        rank = next(
            (
                index
                for index, item in enumerate(retrieved, start=1)
                if item in relevant
            ),
            None,
        )
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
    return sum(reciprocal_ranks) / len(ranked_results)


def context_efficiency_ratio(useful_tokens: int, supplied_tokens: int) -> float:
    if supplied_tokens <= 0:
        return 0.0
    return min(max(useful_tokens / supplied_tokens, 0.0), 1.0)


def token_reduction_ratio(candidate_tokens: int, baseline_tokens: int) -> float:
    if baseline_tokens <= 0:
        return 0.0
    return min(max(1.0 - (candidate_tokens / baseline_tokens), 0.0), 1.0)


def stale_memory_error_rate(stale_retrieved: int, retrieved_total: int) -> float:
    """Placeholder definition until suite-level stale-memory scoring is finalized."""

    if retrieved_total <= 0:
        return 0.0
    return min(max(stale_retrieved / retrieved_total, 0.0), 1.0)


def conflict_resolution_score(resolved: int, conflicts: int) -> float:
    """Placeholder deterministic ratio for explicitly labeled conflicts."""

    if conflicts <= 0:
        return 1.0
    return min(max(resolved / conflicts, 0.0), 1.0)
