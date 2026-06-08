from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from benchmarks.common.mneno_client import (
    INSTALL_MESSAGE,
    MnenoAdapter,
    MnenoNotInstalledError,
)


class FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.memories: list[dict[str, Any]] = []

    def add_memory(self, memory: dict[str, Any]) -> None:
        self.memories.append(memory)

    def evaluate_search(self, query: str, limit: int) -> dict[str, Any]:
        return {
            "query": query,
            "metrics": {"precision": 1.0, "latency_ms": 2.5},
            "trace_id": "trace-search",
            "retrieved_memory_ids": ["mem-1"],
            "limit": limit,
        }


class RealShapeClient:
    def __init__(self) -> None:
        self.added: dict[str, Any] = {}

    def add(
        self,
        content: str,
        *,
        memory_type: str,
        metadata: dict[str, Any],
        session_id: str | None = None,
        layer: str | None = None,
    ) -> dict[str, Any]:
        self.added = {
            "content": content,
            "memory_type": memory_type,
            "metadata": metadata,
            "session_id": session_id,
            "layer": layer,
        }
        return {"id": "internal-1"}

    def evaluate_search(self, query: str, limit: int) -> dict[str, Any]:
        return {
            "query": query,
            "metrics": [{"name": "retrieval_recall", "value": 1.0}],
            "selected_memory_ids": ["internal-1"],
            "limit": limit,
        }


def test_adapter_detects_version_and_calls_evaluation() -> None:
    module = SimpleNamespace(__version__="0.3.4", MemoryClient=FakeClient)
    adapter = MnenoAdapter()
    adapter._module = module

    assert adapter.is_available()
    assert adapter.version() == "0.3.4"

    client = adapter.create_client(trace_enabled=True)
    result = adapter.evaluate_search(
        client=client,
        query="current preference",
        limit=3,
        unsupported_argument=True,
    )

    assert client.kwargs == {"trace_enabled": True}
    assert result.provider == "mneno"
    assert result.metrics["precision"] == 1.0
    assert result.trace_id == "trace-search"


def test_adapter_calls_root_exports() -> None:
    module = SimpleNamespace(
        __version__="0.3.0",
        export_trace=lambda trace_id: {
            "format": "mneno.trace",
            "version": 1,
            "trace": {"id": trace_id},
        },
        export_all_traces=lambda: [],
        export_benchmark_result=lambda result: {
            "format": "mneno.benchmark.result",
            "version": 1,
            "result": result,
        },
    )
    adapter = MnenoAdapter()
    adapter._module = module

    assert adapter.export_trace(trace_id="trace-1")["trace"]["id"] == "trace-1"
    assert adapter.export_all_traces() == []
    assert adapter.export_benchmark(result={"metrics": {}})["version"] == 1


def test_adapter_supports_real_sdk_insertion_and_metric_shapes() -> None:
    adapter = MnenoAdapter()
    client = RealShapeClient()
    adapter.add_memory(
        client,
        {
            "id": "dataset-1",
            "content": "Current task",
            "memory_type": "task",
            "layer": "archive",
            "session_id": "session-1",
            "metadata": {},
        },
    )

    assert client.added["content"] == "Current task"
    assert client.added["memory_type"] == "operational"
    assert client.added["layer"] == "archived"
    assert client.added["metadata"]["dataset_memory_id"] == "dataset-1"

    result = adapter.evaluate_search(
        client=client, query="task", limit=4, unsupported=True
    )
    assert result.metrics == {"retrieval_recall": 1.0}


def test_adapter_missing_sdk_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_: str) -> Any:
        raise ImportError

    monkeypatch.setattr("importlib.import_module", missing)
    adapter = MnenoAdapter()

    assert not adapter.is_available()
    with pytest.raises(MnenoNotInstalledError, match=INSTALL_MESSAGE):
        adapter.create_client()
