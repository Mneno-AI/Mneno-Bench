from benchmarks.locomo.answering import generate_answer_from_context


def test_generate_answer_from_context_extracts_relevant_sentence() -> None:
    candidate = generate_answer_from_context(
        "keyword_baseline",
        "q1",
        "Where did Alex move?",
        "Blair asked about lunch. Alex said I moved to Rome.",
    )

    assert candidate.answer == "Alex said I moved to Rome."
    assert candidate.metadata["official_generation"] is False


def test_generate_answer_from_context_handles_empty_context() -> None:
    candidate = generate_answer_from_context("keyword_baseline", "q1", "Question?", "")

    assert candidate.answer == ""
    assert candidate.context == ""
