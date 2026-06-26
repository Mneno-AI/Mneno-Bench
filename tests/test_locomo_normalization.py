import pytest
from pydantic import ValidationError

from benchmarks.locomo.normalization import NormalizedLOCOMOResult


def test_normalized_locomo_result_serializes() -> None:
    result = NormalizedLOCOMOResult(
        provider="keyword_baseline",
        metrics={"evidence_recall": 0.5, "factual_recall": None},
        trace_ids=["trace-1"],
        metadata={"question_id": "q1"},
    )

    assert result.model_dump(mode="json") == {
        "provider": "keyword_baseline",
        "benchmark": "locomo",
        "metrics": {"evidence_recall": 0.5, "factual_recall": None},
        "official_score": None,
        "diagnostic_score": None,
        "retrieval_diagnostic": None,
        "judge_score": None,
        "trace_ids": ["trace-1"],
        "metadata": {"question_id": "q1"},
    }


def test_normalized_locomo_result_rejects_invalid_schema() -> None:
    with pytest.raises(ValidationError):
        NormalizedLOCOMOResult.model_validate(
            {"provider": "", "benchmark": "locomo", "unexpected": True}
        )
