"""Weighted aggregate score for Mneno Context Rot Suite v1."""

from __future__ import annotations

from collections.abc import Mapping

DEFAULT_CONTEXT_ROT_WEIGHTS: dict[str, float] = {
    "expected_memory_recall": 0.25,
    "stale_memory_suppression_rate": 0.20,
    "forbidden_memory_error_rate_inverse": 0.15,
    "context_efficiency_score": 0.15,
    "lifecycle_alignment_score": 0.10,
    "session_continuity_score": 0.10,
    "explainability_coverage_score": 0.05,
}


def calculate_context_rot_score(
    metrics: Mapping[str, float], weights: Mapping[str, float] | None = None
) -> float:
    configured = dict(weights or DEFAULT_CONTEXT_ROT_WEIGHTS)
    if not configured:
        raise ValueError("Context Rot Score weights cannot be empty.")
    if any(value < 0 for value in configured.values()):
        raise ValueError("Context Rot Score weights cannot be negative.")
    total_weight = sum(configured.values())
    if total_weight <= 0:
        raise ValueError("Context Rot Score weights must have a positive sum.")

    values = dict(metrics)
    values["forbidden_memory_error_rate_inverse"] = 1.0 - values.get(
        "forbidden_memory_error_rate", 0.0
    )
    weighted = sum(
        min(max(values.get(name, 0.0), 0.0), 1.0) * weight
        for name, weight in configured.items()
    )
    return round(weighted / total_weight, 6)
