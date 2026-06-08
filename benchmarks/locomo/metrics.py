"""LOCOMO retrieval diagnostics and official-compatible QA metrics."""

from __future__ import annotations

import re
import string
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Literal

from nltk.stem import PorterStemmer  # type: ignore[import-untyped,import-not-found]
from pydantic import BaseModel, Field

from benchmarks.common.schema import MetricResult

LOCOMOMetricName = Literal[
    "factual_recall",
    "temporal_reasoning",
    "multi_hop_reasoning",
    "multi_session_reasoning",
]

OFFICIAL_SCORING_PENDING = "Official LOCOMO answer evaluation is unavailable."
_PORTER_STEMMER = PorterStemmer()


class LOCOMOMetricDefinition(BaseModel):
    name: LOCOMOMetricName
    description: str
    direction: Literal["higher", "lower"] = "higher"
    methodology: str = "official_locomo_pending"


class LOCOMOMetricAggregate(BaseModel):
    name: LOCOMOMetricName
    numerator: float | None = None
    denominator: int = Field(default=0, ge=0)
    value: float | None = None
    unavailable_reason: str | None = OFFICIAL_SCORING_PENDING


METRIC_DEFINITIONS = (
    LOCOMOMetricDefinition(
        name="factual_recall",
        description="LOCOMO single-hop question-answering score.",
    ),
    LOCOMOMetricDefinition(
        name="temporal_reasoning",
        description="LOCOMO temporal question-answering score.",
    ),
    LOCOMOMetricDefinition(
        name="multi_hop_reasoning",
        description="LOCOMO multi-hop question-answering score.",
    ),
    LOCOMOMetricDefinition(
        name="multi_session_reasoning",
        description="Cross-session answer diagnostic.",
    ),
)


def official_metric_placeholders() -> list[MetricResult]:
    return [
        MetricResult(
            name=definition.name,
            value=None,
            description=definition.description,
            unavailable_reason=OFFICIAL_SCORING_PENDING,
            metadata={
                "direction": definition.direction,
                "methodology": definition.methodology,
            },
        )
        for definition in METRIC_DEFINITIONS
    ]


def evidence_recall(
    retrieved_ids: Iterable[str], evidence_ids: Iterable[str]
) -> float | None:
    expected = set(evidence_ids)
    if not expected:
        return None
    return round(len(expected & set(retrieved_ids)) / len(expected), 6)


def evidence_precision(
    retrieved_ids: Iterable[str], evidence_ids: Iterable[str]
) -> float | None:
    retrieved = set(retrieved_ids)
    if not retrieved:
        return None
    return round(len(retrieved & set(evidence_ids)) / len(retrieved), 6)


def retrieval_hit_rate(
    retrieved_ids: Iterable[str], evidence_ids: Iterable[str]
) -> float | None:
    expected = set(evidence_ids)
    if not expected:
        return None
    return 1.0 if expected & set(retrieved_ids) else 0.0


def exact_match(prediction: str, ground_truth: str) -> float:
    return 1.0 if prediction == ground_truth else 0.0


def normalized_exact_match(prediction: str, ground_truth: str) -> float:
    return (
        1.0 if normalize_answer(prediction) == normalize_answer(ground_truth) else 0.0
    )


def contains_answer(prediction: str, ground_truth: str) -> float:
    normalized_prediction = normalize_answer(prediction)
    normalized_truth = normalize_answer(ground_truth)
    if not normalized_truth:
        return 0.0
    return 1.0 if normalized_truth in normalized_prediction else 0.0


def token_f1(prediction: str, ground_truth: str) -> float:
    prediction_tokens = normalize_answer(prediction).split()
    ground_truth_tokens = normalize_answer(ground_truth).split()
    if not prediction_tokens or not ground_truth_tokens:
        return 1.0 if prediction_tokens == ground_truth_tokens else 0.0
    common = Counter(_stem(token) for token in prediction_tokens) & Counter(
        _stem(token) for token in ground_truth_tokens
    )
    same = sum(common.values())
    if same == 0:
        return 0.0
    precision = same / len(prediction_tokens)
    recall = same / len(ground_truth_tokens)
    return round((2 * precision * recall) / (precision + recall), 6)


def multi_answer_f1(prediction: str, ground_truth: str) -> float:
    predictions = [part.strip() for part in prediction.split(",") if part.strip()]
    ground_truths = [part.strip() for part in ground_truth.split(",") if part.strip()]
    if not predictions or not ground_truths:
        return token_f1(prediction, ground_truth)
    scores = [
        max(token_f1(item, truth) for item in predictions) for truth in ground_truths
    ]
    return round(sum(scores) / len(scores), 6)


def answer_diagnostic_score(prediction: str, ground_truth: str) -> float:
    return max(
        normalized_exact_match(prediction, ground_truth),
        contains_answer(prediction, ground_truth),
        token_f1(prediction, ground_truth),
    )


def official_locomo_qa_score(
    prediction: str, ground_truth: str | None, category: int | str
) -> float | None:
    """Reproduce the released LOCOMO QA category/F1 scoring implementation."""

    category_value = (
        int(category) if isinstance(category, int) or str(category).isdigit() else None
    )
    if category_value == 5:
        return 1.0 if _is_no_information_answer(prediction) else 0.0
    if ground_truth is None or ground_truth == "":
        return None
    answer = ground_truth.split(";")[0].strip() if category_value == 3 else ground_truth
    if category_value == 1:
        return multi_answer_f1(prediction, answer)
    if category_value in {2, 3, 4}:
        return token_f1(prediction, answer)
    return None


def normalize_answer(value: str) -> str:
    value = value.replace(",", "").lower()
    value = "".join(ch for ch in value if ch not in set(string.punctuation))
    value = re.sub(r"\b(a|an|the|and)\b", " ", value)
    return " ".join(value.split())


def average_available(values: Iterable[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    if not available:
        return None
    return round(sum(available) / len(available), 6)


def aggregate_metric_maps(
    values: Iterable[Mapping[str, float | int | None]],
) -> dict[str, float | None]:
    rows = list(values)
    names = sorted({name for row in rows for name in row})
    return {
        name: average_available(_numeric_value(row.get(name)) for row in rows)
        for name in names
    }


def _numeric_value(value: float | int | None) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    return float(value)


def _is_no_information_answer(value: str) -> bool:
    normalized = value.lower()
    return "no information available" in normalized or "not mentioned" in normalized


def _stem(value: str) -> str:
    return _PORTER_STEMMER.stem(value)
