from benchmarks.common.metrics import (
    context_efficiency_ratio,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    stale_memory_error_rate,
    token_reduction_ratio,
)


def test_retrieval_metrics_are_deterministic() -> None:
    retrieved = ["a", "noise", "b"]
    relevant = ["a", "b"]

    assert precision_at_k(retrieved, relevant, 3) == 2 / 3
    assert recall_at_k(retrieved, relevant, 3) == 1.0
    assert mean_reciprocal_rank([retrieved], [relevant]) == 1.0


def test_context_metrics_are_bounded() -> None:
    assert context_efficiency_ratio(25, 100) == 0.25
    assert token_reduction_ratio(25, 100) == 0.75
    assert stale_memory_error_rate(1, 4) == 0.25
