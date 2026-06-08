"""Deterministic LOCOMO answer candidate generation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnswerCandidate(BaseModel):
    """One answer produced for LOCOMO scoring or judging."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    question_id: str
    answer: str
    context: str
    trace_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "question_id")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


def generate_answer_from_context(
    provider: str,
    question_id: str,
    question: str,
    context: str,
    trace_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AnswerCandidate:
    """Return a local extractive diagnostic answer, not an LLM response."""

    answer = _extractive_answer(question, context)
    return AnswerCandidate(
        provider=provider,
        question_id=question_id,
        answer=answer,
        context=context,
        trace_ids=trace_ids or [],
        metadata={
            "generation_method": "deterministic_extractive_diagnostic",
            "official_generation": False,
            **(metadata or {}),
        },
    )


def _extractive_answer(question: str, context: str) -> str:
    if not context.strip():
        return ""
    question_terms = _terms(question)
    best_sentence = ""
    best_score = -1
    for sentence in _sentences(context):
        terms = _terms(sentence)
        score = len(question_terms & terms)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    return best_sentence.strip()


def _sentences(value: str) -> list[str]:
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", value)]
    return [sentence for sentence in sentences if sentence]


def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2
    }
