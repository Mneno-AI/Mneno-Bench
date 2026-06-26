"""Configuration for LOCOMO evaluation modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

LOCOMOEvaluationMode = Literal["retrieval_only", "deterministic_answer", "llm_judge"]
LOCOMOExecutionPhase = Literal["full", "predict_only", "evaluate_only"]


class LOCOMOEvaluationConfig(BaseModel):
    """Runtime controls for optional LOCOMO answer evaluation."""

    model_config = ConfigDict(extra="forbid")

    mode: LOCOMOEvaluationMode = "retrieval_only"
    judge_model: str | None = None
    judge_provider: str | None = None
    max_cases: int | None = Field(default=None, ge=1)
    workers: int = Field(default=1, ge=1)
    strict_dataset_validation: bool = True
    allow_malformed_evidence: bool = False
    save_judge_prompts: bool = True
    prompt_version: str = "locomo_judge_v1"
    judge_config_path: str | None = None
    allow_external_calls: bool = False
    mneno_reranker_model: str | None = None
    mneno_reranker_provider: str | None = None
    mneno_reranker_api_base: str | None = None
    mneno_reranker_api_key_required: bool = True
    mneno_reranker_candidate_limit: int = Field(default=50, ge=1, le=512)
    mneno_reranker_cache_size: int = Field(default=4096, ge=1)
    mneno_reranker_timeout_seconds: float = Field(default=60.0, gt=0)
    mneno_reranker_retries: int = Field(default=2, ge=0, le=10)
    external_requests_per_minute: int | None = Field(default=60, ge=1)
    external_max_concurrent_requests: int = Field(default=1, ge=1)
    external_retries: int = Field(default=2, ge=0, le=10)
    external_retry_backoff_seconds: float = Field(default=1.0, ge=0.0)
    external_retry_backoff_max_seconds: float = Field(default=30.0, ge=0.0)
    external_retry_jitter_seconds: float = Field(default=0.25, ge=0.0)
    resume: bool = False
    reuse_failed_checkpoints: bool = False
    checkpoint_dir: str | None = None
    output_dir: str | None = None
    phase: LOCOMOExecutionPhase = "full"

    @model_validator(mode="after")
    def validate_dataset_flags(self) -> "LOCOMOEvaluationConfig":
        if self.strict_dataset_validation and self.allow_malformed_evidence:
            raise ValueError(
                "allow_malformed_evidence requires strict_dataset_validation=False"
            )
        if self.mneno_reranker_model and not self.allow_external_calls:
            raise ValueError("mneno_reranker_model requires allow_external_calls=True")
        if self.phase == "evaluate_only" and not self.resume:
            raise ValueError("phase='evaluate_only' requires resume=True")
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
