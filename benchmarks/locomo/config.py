"""Configuration for LOCOMO evaluation modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

LOCOMOEvaluationMode = Literal["retrieval_only", "deterministic_answer", "llm_judge"]


class LOCOMOEvaluationConfig(BaseModel):
    """Runtime controls for optional LOCOMO answer evaluation."""

    model_config = ConfigDict(extra="forbid")

    mode: LOCOMOEvaluationMode = "retrieval_only"
    judge_model: str | None = None
    judge_provider: str | None = None
    max_cases: int | None = Field(default=None, ge=1)
    strict_dataset_validation: bool = True
    allow_malformed_evidence: bool = False
    save_judge_prompts: bool = True
    prompt_version: str = "locomo_judge_v1"
    judge_config_path: str | None = None
    allow_external_calls: bool = False

    @model_validator(mode="after")
    def validate_dataset_flags(self) -> "LOCOMOEvaluationConfig":
        if self.strict_dataset_validation and self.allow_malformed_evidence:
            raise ValueError(
                "allow_malformed_evidence requires strict_dataset_validation=False"
            )
        return self

    @classmethod
    def from_yaml(
        cls, path: str | Path, overrides: dict[str, Any] | None = None
    ) -> "LOCOMOEvaluationConfig":
        with Path(path).open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"LOCOMO config must be a mapping: {path}")
        return cls.model_validate({**raw, **(overrides or {})})
