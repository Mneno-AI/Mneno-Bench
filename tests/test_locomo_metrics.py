from benchmarks.locomo.metrics import (
    answer_diagnostic_score,
    contains_answer,
    evidence_precision,
    evidence_recall,
    exact_match,
    normalized_exact_match,
    official_locomo_qa_score,
    retrieval_hit_rate,
    token_f1,
)


def test_retrieval_diagnostics() -> None:
    assert evidence_recall(["a", "b"], ["b", "c"]) == 0.5
    assert evidence_precision(["a", "b"], ["b", "c"]) == 0.5
    assert retrieval_hit_rate(["a"], ["b"]) == 0.0
    assert retrieval_hit_rate(["a"], ["a", "b"]) == 1.0


def test_answer_diagnostic_metrics() -> None:
    assert exact_match("Rome", "Rome") == 1.0
    assert normalized_exact_match("The Rome!", "rome") == 1.0
    assert contains_answer("Alex moved to Rome", "Rome") == 1.0
    assert token_f1("moved to Rome", "Rome") > 0.0
    assert answer_diagnostic_score("Alex moved to Rome", "Rome") == 1.0


def test_official_locomo_category_scoring() -> None:
    assert official_locomo_qa_score("Rome", "Rome", 2) == 1.0
    assert official_locomo_qa_score("Python, Rome", "Rome, Python", 1) == 1.0
    assert official_locomo_qa_score("No information available", None, 5) == 1.0
    assert official_locomo_qa_score("Some answer", None, 5) == 0.0
