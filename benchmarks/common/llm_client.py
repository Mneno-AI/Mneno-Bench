"""LiteLLM-ready generation boundary for future judge-based evaluations."""

from __future__ import annotations

import os
import random
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock
from typing import Any, TypeVar

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_API_KEY_ENV = "LITELLM_API_KEY"
MODEL_API_BASE_ENV = "LITELLM_API_BASE"
T = TypeVar("T")


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    provider: str | None = None
    api_base: str | None = None
    api_key_required: bool = True
    temperature: float = 0.0
    max_tokens: int = 512
    requests_per_minute: int | None = Field(default=None, ge=1)
    max_concurrent_requests: int = Field(default=1, ge=1)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=1.0, ge=0.0)
    retry_backoff_max_seconds: float = Field(default=30.0, ge=0.0)
    retry_jitter_seconds: float = Field(default=0.25, ge=0.0)
    extra: dict[str, Any] = Field(default_factory=dict)


class _LimiterStats:
    def __init__(self) -> None:
        self.successful_requests = 0
        self.attempts = 0
        self.retries = 0
        self.rate_limited_429s = 0
        self.failures = 0
        self.retry_after_seconds = 0.0
        self._lock = Lock()

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "successful_requests": self.successful_requests,
                "attempts": self.attempts,
                "retries": self.retries,
                "rate_limited_429s": self.rate_limited_429s,
                "failures": self.failures,
                "retry_after_seconds": round(self.retry_after_seconds, 4),
            }

    def add(self, key: str, amount: int | float = 1) -> None:
        with self._lock:
            current = getattr(self, key)
            setattr(self, key, current + amount)


class ThreadSharedRateLimiter:
    """Simple thread-shared start-rate and concurrency limiter."""

    def __init__(self, requests_per_minute: int | None, max_concurrent: int) -> None:
        self.requests_per_minute = requests_per_minute
        self.max_concurrent = max(1, max_concurrent)
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent)
        self._lock = Lock()
        self._next_available_at = 0.0

    def __enter__(self) -> "ThreadSharedRateLimiter":
        self._semaphore.acquire()
        try:
            self._wait_for_turn()
        except BaseException:
            self._semaphore.release()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self._semaphore.release()

    def _wait_for_turn(self) -> None:
        if not self.requests_per_minute:
            return
        interval = 60.0 / float(self.requests_per_minute)
        with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_available_at - now)
            if wait_seconds:
                time.sleep(wait_seconds)
                now = time.monotonic()
            self._next_available_at = max(self._next_available_at, now) + interval


_global_limiters: dict[tuple[str, str | None, str | None, int | None, int], ThreadSharedRateLimiter] = {}
_global_stats: dict[tuple[str, str | None, str | None], _LimiterStats] = {}
_global_lock = Lock()


class LLMClient:
    """Load provider configuration and gate all external model calls."""

    def __init__(self, config: LLMConfig, allow_external_calls: bool = False) -> None:
        _load_project_dotenv()
        self.config = config
        self.allow_external_calls = allow_external_calls
        self._limiter = _shared_limiter(config)
        self._stats = _shared_stats(config)

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

    @staticmethod
    def global_stats() -> dict[str, int | float]:
        totals: dict[str, int | float] = {
            "successful_requests": 0,
            "attempts": 0,
            "retries": 0,
            "rate_limited_429s": 0,
            "failures": 0,
            "retry_after_seconds": 0.0,
        }
        with _global_lock:
            snapshots = [stats.snapshot() for stats in _global_stats.values()]
        for snapshot in snapshots:
            for key, value in snapshot.items():
                totals[key] = totals.get(key, 0) + value
        totals["retry_after_seconds"] = round(float(totals["retry_after_seconds"]), 4)
        return totals

    def stats(self) -> dict[str, int | float]:
        return self._stats.snapshot()

    def generate(self, prompt: str, **overrides: Any) -> str:
        """Generate text through LiteLLM only when explicitly enabled."""

        self._require_external_calls()

        from litellm import completion

        request = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            **self.config.extra,
            **overrides,
        }
        request.update(self._connection_request())

        response = self._call_with_retry("completion", lambda: completion(**request))
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("LiteLLM completion returned empty content.")
        return str(content)

    def rerank(self, query: str, documents: list[str], **overrides: Any) -> list[int]:
        """Return provider-ranked document indices through LiteLLM."""

        if not documents:
            return []
        self._require_external_calls()

        from litellm import rerank

        request = {
            "model": self.config.model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
            "return_documents": False,
            **self.config.extra,
            **overrides,
        }
        request.update(self._connection_request())
        response = self._call_with_retry("rerank", lambda: rerank(**request))
        return _reranked_indices(response, len(documents))

    def _call_with_retry(self, operation: str, call: Callable[[], T]) -> T:
        max_retries = int(self.config.max_retries)
        attempt_count = max_retries + 1
        last_exc: Exception | None = None
        for attempt in range(1, attempt_count + 1):
            self._stats.add("attempts")
            try:
                with self._limiter:
                    result = call()
                self._stats.add("successful_requests")
                return result
            except Exception as exc:  # noqa: BLE001 - provider exceptions vary.
                last_exc = exc
                status = _status_code(exc)
                if status == 429:
                    self._stats.add("rate_limited_429s")
                if attempt >= attempt_count or not _is_retryable(exc):
                    self._stats.add("failures")
                    raise RuntimeError(
                        _external_call_error(operation, self.config.model, exc, attempt)
                    ) from None
                self._stats.add("retries")
                retry_after = _retry_after_seconds(exc)
                delay = (
                    retry_after
                    if retry_after is not None
                    else _backoff_delay(self.config, attempt)
                )
                if retry_after is not None:
                    self._stats.add("retry_after_seconds", retry_after)
                if delay > 0:
                    time.sleep(delay)
        assert last_exc is not None
        self._stats.add("failures")
        raise RuntimeError(
            _external_call_error(operation, self.config.model, last_exc, attempt_count)
        ) from None

    def _require_external_calls(self) -> None:
        if not self.allow_external_calls:
            raise RuntimeError(
                "External LLM calls are disabled. Set allow_external_calls=True "
                "only for an explicitly configured benchmark run."
            )

    def _connection_request(self) -> dict[str, str]:
        request: dict[str, str] = {}
        api_key = os.getenv(MODEL_API_KEY_ENV)
        if self.config.api_key_required and not api_key:
            raise RuntimeError(
                f"Model API key is missing. Set {MODEL_API_KEY_ENV} in .env."
            )
        if api_key:
            request["api_key"] = api_key
        api_base = self.config.api_base or os.getenv(MODEL_API_BASE_ENV)
        if api_base:
            request["api_base"] = api_base
        return request


class CachedRerankerProvider:
    """Mneno-compatible reranker with bounded candidates and request caching."""

    def __init__(
        self,
        client: LLMClient,
        *,
        candidate_limit: int = 50,
        cache_size: int = 4096,
    ) -> None:
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be greater than 0")
        if cache_size <= 0:
            raise ValueError("cache_size must be greater than 0")
        self.client = client
        self.candidate_limit = candidate_limit
        self.cache_size = cache_size
        self.name = f"litellm:{client.config.model}"
        self._cache: OrderedDict[tuple[str, tuple[str, ...]], tuple[int, ...]] = (
            OrderedDict()
        )
        self._lock = Lock()
        self._api_requests = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._documents_sent = 0

    def rerank(self, query: str, documents: list[str]) -> list[int]:
        """Rerank the strongest candidate prefix; Mneno preserves the tail."""

        selected = documents[: self.candidate_limit]
        if not selected:
            return []
        key = (query, tuple(selected))
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._cache_hits += 1
                return list(cached)
            self._cache_misses += 1

        with self._lock:
            self._api_requests += 1
            self._documents_sent += len(selected)
        indices = self.client.rerank(query, selected)
        with self._lock:
            self._cache[key] = tuple(indices)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return indices

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "model": self.client.config.model,
                "provider": self.client.config.provider,
                "candidate_limit": self.candidate_limit,
                "cache_size": self.cache_size,
                "cache_entries": len(self._cache),
                "api_requests": self._api_requests,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "documents_sent": self._documents_sent,
                "external_request_stats": self.client.stats(),
            }


def _load_project_dotenv() -> None:
    if os.environ.get(MODEL_API_KEY_ENV) == "":
        os.environ.pop(MODEL_API_KEY_ENV, None)
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _shared_limiter(config: LLMConfig) -> ThreadSharedRateLimiter:
    key = (
        config.model,
        config.provider,
        config.api_base,
        config.requests_per_minute,
        config.max_concurrent_requests,
    )
    with _global_lock:
        limiter = _global_limiters.get(key)
        if limiter is None:
            limiter = ThreadSharedRateLimiter(
                config.requests_per_minute, config.max_concurrent_requests
            )
            _global_limiters[key] = limiter
        return limiter


def _shared_stats(config: LLMConfig) -> _LimiterStats:
    key = (config.model, config.provider, config.api_base)
    with _global_lock:
        stats = _global_stats.get(key)
        if stats is None:
            stats = _LimiterStats()
            _global_stats[key] = stats
        return stats


def _external_call_error(
    operation: str, model: str, exc: Exception, attempts: int | None = None
) -> str:
    message = str(exc).strip() or repr(exc)
    attempt_text = f" after {attempts} attempt(s)" if attempts is not None else ""
    return (
        f"LiteLLM {operation} failed for model {model!r}{attempt_text} "
        f"({type(exc).__name__}): {message}"
    )


def _is_retryable(exc: Exception) -> bool:
    status = _status_code(exc)
    if status == 429 or (status is not None and 500 <= status <= 599):
        return True
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return any(
        marker in name or marker in text
        for marker in (
            "timeout",
            "temporar",
            "connection",
            "connecterror",
            "readtimeout",
            "service unavailable",
        )
    )


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            value = getattr(response, attr, None)
            if isinstance(value, int):
                return value
    return None


def _retry_after_seconds(exc: Exception) -> float | None:
    headers = getattr(exc, "headers", None)
    response = getattr(exc, "response", None)
    if headers is None and response is not None:
        headers = getattr(response, "headers", None)
    value: Any = None
    if isinstance(headers, Mapping):
        value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        value = getattr(exc, "retry_after", None)
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, seconds)


def _backoff_delay(config: LLMConfig, attempt: int) -> float:
    base = float(config.retry_backoff_seconds)
    cap = float(config.retry_backoff_max_seconds)
    jitter = random.uniform(0, float(config.retry_jitter_seconds))
    return min(cap, base * (2 ** max(attempt - 1, 0))) + jitter


def _reranked_indices(response: Any, document_count: int) -> list[int]:
    items = _field(response, "results")
    if items is None:
        items = _field(response, "rankings")
    if not isinstance(items, list):
        raise RuntimeError("Reranker returned no ranked result list.")

    indices: list[int] = []
    for item in items:
        index = _field(item, "index")
        if not isinstance(index, int):
            raise RuntimeError("Reranker returned a non-integer document index.")
        if index < 0 or index >= document_count:
            raise RuntimeError(f"Reranker index out of range: {index}")
        if index in indices:
            raise RuntimeError(f"Reranker returned duplicate index: {index}")
        indices.append(index)
    return indices


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)
