"""System-independent metric comparison for normalized evaluation results."""

from __future__ import annotations

from typing import Any, TypeGuard

from pydantic import BaseModel, Field

from benchmarks.common.schema import (
    NormalizedCompactionResult,
    NormalizedContextResult,
    NormalizedSearchResult,
)

NormalizedResult = (
    NormalizedSearchResult | NormalizedContextResult | NormalizedCompactionResult
)


class ComparisonResult(BaseModel):
    benchmark: str
    baseline: str
    candidate: str
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    summary: str


def compare_results(
    baseline: NormalizedResult,
    candidate: NormalizedResult,
    benchmark: str = "normalized_evaluation",
) -> ComparisonResult:
    metric_deltas: dict[str, float] = {}
    for name in sorted(set(baseline.metrics) & set(candidate.metrics)):
        baseline_value = baseline.metrics[name]
        candidate_value = candidate.metrics[name]
        if _is_number(baseline_value) and _is_number(candidate_value):
            metric_deltas[name] = round(
                float(candidate_value) - float(baseline_value), 6
            )
    improved = sum(value > 0 for value in metric_deltas.values())
    regressed = sum(value < 0 for value in metric_deltas.values())
    summary = (
        f"{candidate.provider} vs {baseline.provider}: "
        f"{improved} positive, {regressed} negative, "
        f"{len(metric_deltas) - improved - regressed} unchanged metric deltas."
    )
    return ComparisonResult(
        benchmark=benchmark,
        baseline=baseline.provider,
        candidate=candidate.provider,
        metric_deltas=metric_deltas,
        summary=summary,
    )


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
