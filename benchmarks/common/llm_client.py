"""LiteLLM-ready generation boundary for future judge-based evaluations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    provider: str | None = None
    api_base: str | None = None
    temperature: float = 0.0
    max_tokens: int = 512
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMClient:
    """Load provider configuration and gate all external model calls."""

    def __init__(self, config: LLMConfig, allow_external_calls: bool = False) -> None:
        self.config = config
        self.allow_external_calls = allow_external_calls

    @classmethod
    def from_yaml(
        cls, path: str | Path, allow_external_calls: bool = False
    ) -> "LLMClient":
        with Path(path).open(encoding="utf-8") as handle:
            raw_config = yaml.safe_load(handle) or {}
        return cls(
            LLMConfig.model_validate(raw_config),
            allow_external_calls=allow_external_calls,
        )

    def generate(self, prompt: str, **overrides: Any) -> str:
        """Generate text through LiteLLM only when explicitly enabled."""

        if not self.allow_external_calls:
            raise RuntimeError(
                "External LLM calls are disabled. Set allow_external_calls=True "
                "only for an explicitly configured benchmark run."
            )

        from litellm import completion

        request = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            **self.config.extra,
            **overrides,
        }
        if self.config.api_base:
            request["api_base"] = self.config.api_base
        response = completion(**request)
        content = response.choices[0].message.content
        return "" if content is None else str(content)
