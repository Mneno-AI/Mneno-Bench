import pytest

from benchmarks.mneno_suite.scoring import calculate_context_rot_score


def test_context_rot_score_uses_default_weights() -> None:
    metrics = {
        "expected_memory_recall": 1.0,
        "stale_memory_suppression_rate": 1.0,
        "forbidden_memory_error_rate": 0.0,
        "context_efficiency_score": 1.0,
        "lifecycle_alignment_score": 1.0,
        "session_continuity_score": 1.0,
        "explainability_coverage_score": 1.0,
    }
    assert calculate_context_rot_score(metrics) == 1.0


def test_context_rot_score_accepts_custom_weights() -> None:
    score = calculate_context_rot_score(
        {"expected_memory_recall": 0.5, "context_efficiency_score": 1.0},
        {"expected_memory_recall": 1.0, "context_efficiency_score": 1.0},
    )
    assert score == 0.75

    with pytest.raises(ValueError, match="positive sum"):
        calculate_context_rot_score({}, {"expected_memory_recall": 0.0})
