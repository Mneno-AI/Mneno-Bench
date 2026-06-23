import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from benchmarks.common.llm_client import (
    CachedRerankerProvider,
    LLMClient,
    LLMConfig,
)


@pytest.fixture(autouse=True)
def _isolate_project_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "benchmarks.common.llm_client.load_dotenv",
        lambda *args, **kwargs: False,
    )


def _install_fake_litellm(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []

    def completion(**request: Any) -> SimpleNamespace:
        requests.append(request)
        message = SimpleNamespace(content="ok")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=completion))
    return requests


def test_client_passes_shared_litellm_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _install_fake_litellm(monkeypatch)
    monkeypatch.setenv("LITELLM_API_KEY", "shared-key")
    client = LLMClient(
        LLMConfig(model="nvidia_nim/meta/llama-3.1-70b-instruct"),
        allow_external_calls=True,
    )

    assert client.generate("hello") == "ok"
    assert requests[0]["api_key"] == "shared-key"


def test_empty_exported_api_key_loads_project_dotenv_in_parent_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _install_fake_litellm(monkeypatch)

    def fake_load_dotenv(*args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        if "LITELLM_API_KEY" not in __import__("os").environ:
            monkeypatch.setenv("LITELLM_API_KEY", "project-key")
        return True

    monkeypatch.setenv("LITELLM_API_KEY", "")
    monkeypatch.setattr("benchmarks.common.llm_client.load_dotenv", fake_load_dotenv)
    client = LLMClient(LLMConfig(model="dotenv-parent-model"), allow_external_calls=True)

    assert client.generate("hello") == "ok"
    assert requests[0]["api_key"] == "project-key"


def test_empty_exported_api_key_loads_project_dotenv_in_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _install_fake_litellm(monkeypatch)

    def fake_load_dotenv(*args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        if "LITELLM_API_KEY" not in __import__("os").environ:
            monkeypatch.setenv("LITELLM_API_KEY", "project-key-thread")
        return True

    monkeypatch.setenv("LITELLM_API_KEY", "")
    monkeypatch.setattr("benchmarks.common.llm_client.load_dotenv", fake_load_dotenv)

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(
            lambda: LLMClient(
                LLMConfig(model="dotenv-worker-model"), allow_external_calls=True
            ).generate("hello")
        ).result()

    assert result == "ok"
    assert requests[0]["api_key"] == "project-key-thread"


def test_client_skips_remote_call_when_shared_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_litellm(monkeypatch)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    client = LLMClient(
        LLMConfig(model="openai/gpt-4o-mini"),
        allow_external_calls=True,
    )

    with pytest.raises(RuntimeError, match="LITELLM_API_KEY"):
        client.generate("hello")


def test_client_allows_keyless_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_fake_litellm(monkeypatch)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    client = LLMClient(
        LLMConfig(model="ollama/llama3.2", api_key_required=False),
        allow_external_calls=True,
    )

    assert client.generate("hello") == "ok"
    assert "api_key" not in requests[0]


def test_client_reranks_through_litellm_with_shared_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    def rerank(**request: Any) -> SimpleNamespace:
        requests.append(request)
        return SimpleNamespace(
            results=[SimpleNamespace(index=1), SimpleNamespace(index=0)]
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=rerank))
    monkeypatch.setenv("LITELLM_API_KEY", "shared-key")
    client = LLMClient(
        LLMConfig(
            model="nvidia_nim/ranking/nvidia/reranker",
            api_base="https://ai.api.nvidia.com",
        ),
        allow_external_calls=True,
    )

    assert client.rerank("query", ["first", "second"]) == [1, 0]
    assert requests[0]["api_key"] == "shared-key"
    assert requests[0]["api_base"] == "https://ai.api.nvidia.com"
    assert requests[0]["top_n"] == 2


def test_client_wraps_litellm_rerank_errors_as_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProviderError(Exception):
        pass

    def rerank(**request: Any) -> None:
        del request
        raise ProviderError("404 page not found")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=rerank))
    monkeypatch.setenv("LITELLM_API_KEY", "shared-key")
    client = LLMClient(
        LLMConfig(model="nvidia_nim/ranking/nvidia/reranker"),
        allow_external_calls=True,
    )

    with pytest.raises(RuntimeError, match="LiteLLM rerank failed") as exc_info:
        client.rerank("query", ["first"])

    assert "ProviderError" in str(exc_info.value)
    assert "404 page not found" in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_client_retries_429_and_respects_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    class RateLimitError(Exception):
        status_code = 429
        headers = {"Retry-After": "2.5"}

    def rerank(**request: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError("too many requests")
        return {"results": [{"index": 0}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=rerank))
    monkeypatch.setattr("benchmarks.common.llm_client.time.sleep", sleeps.append)
    client = LLMClient(
        LLMConfig(
            model="retry-after-test-model",
            api_key_required=False,
            max_retries=1,
            retry_jitter_seconds=0,
        ),
        allow_external_calls=True,
    )

    assert client.rerank("query", ["doc"]) == [0]
    assert attempts == 2
    assert sleeps == [2.5]
    stats = client.stats()
    assert stats["attempts"] >= 2
    assert stats["retries"] >= 1
    assert stats["rate_limited_429s"] >= 1


def test_clients_with_same_model_share_thread_rate_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    def rerank(**request: Any) -> dict[str, Any]:
        return {"results": [{"index": 0}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=rerank))
    monkeypatch.setattr("benchmarks.common.llm_client.time.monotonic", lambda: now[0])
    monkeypatch.setattr("benchmarks.common.llm_client.time.sleep", sleep)
    config = LLMConfig(
        model="shared-rate-test-model",
        api_key_required=False,
        requests_per_minute=60,
        max_concurrent_requests=1,
    )

    assert LLMClient(config, allow_external_calls=True).rerank("q1", ["a"]) == [0]
    assert LLMClient(config, allow_external_calls=True).rerank("q2", ["b"]) == [0]

    assert sleeps == [1.0]


def test_cached_reranker_limits_candidates_and_reuses_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    def rerank(**request: Any) -> dict[str, Any]:
        requests.append(request)
        return {"rankings": [{"index": 1}, {"index": 0}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=rerank))
    client = LLMClient(
        LLMConfig(model="nvidia_nim/ranking/nvidia/reranker", api_key_required=False),
        allow_external_calls=True,
    )
    provider = CachedRerankerProvider(client, candidate_limit=2, cache_size=4)

    documents = ["first", "second", "not sent"]
    assert provider.rerank("query", documents) == [1, 0]
    assert provider.rerank("query", documents) == [1, 0]

    assert requests[0]["documents"] == ["first", "second"]
    assert len(requests) == 1
    assert provider.metadata()["api_requests"] == 1
    assert provider.metadata()["cache_hits"] == 1
