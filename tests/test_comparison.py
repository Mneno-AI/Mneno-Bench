from benchmarks.common.comparison import compare_results
from benchmarks.common.schema import NormalizedSearchResult


def test_comparison_calculates_metric_deltas_and_summary() -> None:
    baseline = NormalizedSearchResult(
        provider="keyword",
        query="q",
        metrics={"precision": 0.5, "recall": 1.0, "latency_ms": 5.0},
    )
    candidate = NormalizedSearchResult(
        provider="mneno",
        query="q",
        metrics={"precision": 1.0, "recall": 1.0, "latency_ms": 3.0},
    )

    comparison = compare_results(baseline, candidate, benchmark="search")

    assert comparison.metric_deltas == {
        "latency_ms": -2.0,
        "precision": 0.5,
        "recall": 0.0,
    }
    assert comparison.summary == (
        "mneno vs keyword: 1 positive, 1 negative, 1 unchanged metric deltas."
    )
