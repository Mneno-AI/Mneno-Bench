"""Provider-neutral LOCOMO result normalization."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NormalizedLOCOMOResult(BaseModel):
    """Comparable output for one system on one LOCOMO question."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    benchmark: str = "locomo"
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    official_score: float | None = None
    diagnostic_score: float | None = None
    retrieval_diagnostic: float | None = None
    judge_score: float | None = None
    trace_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "benchmark")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value
