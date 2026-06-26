"""Optional LiteLLM-backed judge for LOCOMO answer quality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from benchmarks.common.llm_client import LLMClient, LLMConfig
from benchmarks.common.utils import save_json
from benchmarks.locomo.answering import AnswerCandidate


class JudgeResult(BaseModel):
    """Validated output from one judge attempt."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    correct: bool | None = None
    reason: str
    raw_response: Any = None
    model: str | None = None
    provider: str | None = None
    prompt_version: str
    status: str = "completed"


class _JudgePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    correct: bool
    score: float | int | None = Field(default=None, ge=0.0, le=1.0)
    reason: str


class GenerationClient(Protocol):
    config: LLMConfig

    def generate(self, prompt: str, **overrides: Any) -> str: ...


class LOCOMOJudge:
    """Own prompt construction, LLM invocation, and JSON validation."""

    def __init__(
        self,
        client: GenerationClient,
        prompt_version: str = "locomo_judge_v1",
        save_prompts: bool = True,
        prompt_dir: Path | None = None,
        response_dir: Path | None = None,
    ) -> None:
        self.client = client
        self.prompt_version = prompt_version
        self.save_prompts = save_prompts
        self.prompt_dir = prompt_dir
        self.response_dir = response_dir

    @classmethod
    def from_config(
        cls,
        model: str,
        provider: str | None = None,
        allow_external_calls: bool = False,
        prompt_version: str = "locomo_judge_v1",
        save_prompts: bool = True,
        prompt_dir: Path | None = None,
        response_dir: Path | None = None,
    ) -> "LOCOMOJudge":
        return cls(
            LLMClient(
                LLMConfig(model=model, provider=provider),
                allow_external_calls=allow_external_calls,
            ),
            prompt_version=prompt_version,
            save_prompts=save_prompts,
            prompt_dir=prompt_dir,
            response_dir=response_dir,
        )

    def evaluate(
        self,
        question: str,
        gold_answer: str,
        candidate: AnswerCandidate,
    ) -> JudgeResult:
        prompt = self.build_prompt(question, gold_answer, candidate)
        if self.save_prompts and self.prompt_dir is not None:
            save_json(
                self.prompt_dir / f"{_safe_name(candidate.question_id)}.json",
                {
                    "question_id": candidate.question_id,
                    "prompt_version": self.prompt_version,
                    "prompt": prompt,
                    "model": self.client.config.model,
                    "provider": self.client.config.provider,
                },
            )
        try:
            raw = self.client.generate(prompt)
        except RuntimeError as exc:
            return self.skipped(candidate.question_id, str(exc))
        except Exception as exc:
            return JudgeResult(
                question_id=candidate.question_id,
                reason=str(exc),
                raw_response=None,
                model=self.client.config.model,
                provider=self.client.config.provider,
                prompt_version=self.prompt_version,
                status="error",
            )
        if self.response_dir is not None:
            save_json(
                self.response_dir / f"{_safe_name(candidate.question_id)}.json",
                {
                    "question_id": candidate.question_id,
                    "prompt_version": self.prompt_version,
                    "raw_response": raw,
                    "model": self.client.config.model,
                    "provider": self.client.config.provider,
                },
            )
        try:
            payload = _JudgePayload.model_validate_json(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            return JudgeResult(
                question_id=candidate.question_id,
                reason=f"Invalid judge JSON: {exc}",
                raw_response=raw,
                model=self.client.config.model,
                provider=self.client.config.provider,
                prompt_version=self.prompt_version,
                status="error",
            )
        score = payload.score
        return JudgeResult(
            question_id=candidate.question_id,
            score=float(
                score if score is not None else (1.0 if payload.correct else 0.0)
            ),
            correct=payload.correct,
            reason=payload.reason,
            raw_response=payload.model_dump(mode="json"),
            model=self.client.config.model,
            provider=self.client.config.provider,
            prompt_version=self.prompt_version,
        )

    def skipped(self, question_id: str, reason: str) -> JudgeResult:
        return JudgeResult(
            question_id=question_id,
            reason=reason,
            model=self.client.config.model,
            provider=self.client.config.provider,
            prompt_version=self.prompt_version,
            status="skipped",
        )

    def build_prompt(
        self, question: str, gold_answer: str, candidate: AnswerCandidate
    ) -> str:
        return (
            "You are evaluating a LOCOMO question-answering prediction.\n"
            "Return strict JSON only with keys: correct, score, reason.\n"
            "correct must be a boolean. score must be a number from 0 to 1.\n"
            "Mark correct only if the predicted answer means the same thing as "
            "the gold answer. For unanswerable gold answers, mark correct only "
            "when the prediction says no information is available.\n\n"
            f"Question: {question}\n"
            f"Gold answer: {gold_answer or 'No information available'}\n"
            f"Predicted answer: {candidate.answer}\n"
            f"Context:\n{candidate.context}\n"
        )


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value) or "item"
