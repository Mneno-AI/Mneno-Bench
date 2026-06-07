"""Optional, version-tolerant adapter around the Mneno Python SDK."""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from benchmarks.common.schema import (
    NormalizedCompactionResult,
    NormalizedContextResult,
    NormalizedSearchResult,
)

INSTALL_MESSAGE = "Install Mneno from PyPI or provide a local wheel."


class MnenoNotInstalledError(RuntimeError):
    """Raised when the optional Mneno SDK cannot be imported."""


MnenoUnavailableError = MnenoNotInstalledError


class MnenoAdapter:
    """Own SDK discovery, calls, and normalization at the optional boundary."""

    def __init__(self, module_name: str = "mneno") -> None:
        self.module_name = module_name
        self._module: Any | None = None

    def is_available(self) -> bool:
        try:
            self._load_module()
        except MnenoNotInstalledError:
            return False
        return True

    def version(self) -> str | None:
        module = self._load_module()
        version = getattr(module, "__version__", None)
        if version is not None:
            return str(version)
        try:
            return importlib.metadata.version(self.module_name)
        except importlib.metadata.PackageNotFoundError:
            return None

    def create_client(self, **kwargs: Any) -> Any:
        client_type = self._resolve_attribute("MemoryClient")
        if not callable(client_type):
            raise RuntimeError("The installed Mneno SDK does not expose MemoryClient.")
        return client_type(**kwargs)

    def evaluate_search(self, *args: Any, **kwargs: Any) -> NormalizedSearchResult:
        raw = self._call_sdk("evaluate_search", *args, **kwargs)
        return NormalizedSearchResult(
            provider="mneno",
            query=str(kwargs.get("query", _value(raw, "query", ""))),
            metrics=_extract_metrics(raw),
            trace_id=_extract_trace_id(raw),
            raw_result=_to_jsonable(raw),
        )

    def evaluate_context(self, *args: Any, **kwargs: Any) -> NormalizedContextResult:
        raw = self._call_sdk("evaluate_context", *args, **kwargs)
        return NormalizedContextResult(
            provider="mneno",
            query=str(kwargs.get("query", _value(raw, "query", ""))),
            metrics=_extract_metrics(raw),
            trace_id=_extract_trace_id(raw),
            raw_result=_to_jsonable(raw),
        )

    def evaluate_compaction(
        self, *args: Any, **kwargs: Any
    ) -> NormalizedCompactionResult:
        raw = self._call_sdk("evaluate_compaction", *args, **kwargs)
        return NormalizedCompactionResult(
            provider="mneno",
            metrics=_extract_metrics(raw),
            trace_id=_extract_trace_id(raw),
            raw_result=_to_jsonable(raw),
        )

    def export_trace(self, *args: Any, **kwargs: Any) -> Any:
        return _to_jsonable(self._call_sdk("export_trace", *args, **kwargs))

    def export_all_traces(self, *args: Any, **kwargs: Any) -> Any:
        return _to_jsonable(self._call_sdk("export_all_traces", *args, **kwargs))

    def export_benchmark(self, *args: Any, **kwargs: Any) -> Any:
        return _to_jsonable(self._call_sdk("export_benchmark_result", *args, **kwargs))

    def add_memory(self, client: Any, memory: Mapping[str, Any]) -> Any:
        method = getattr(client, "add_memory", None) or getattr(client, "add", None)
        if not callable(method):
            raise RuntimeError("Mneno MemoryClient does not expose add_memory/add.")
        try:
            return method(dict(memory))
        except TypeError:
            return method(
                text=str(memory.get("text", "")),
                memory_id=str(memory["id"]),
                metadata={
                    **dict(memory.get("metadata", {})),
                    "memory_type": memory.get("memory_type"),
                    "layer": memory.get("layer"),
                    "status": memory.get("status"),
                    "importance": memory.get("importance"),
                    "session_id": memory.get("session_id"),
                    "sequence_index": memory.get("sequence_index"),
                    "tags": memory.get("tags", []),
                    "superseded_by": memory.get("superseded_by"),
                    "created_at": memory.get("created_at"),
                },
            )

    def search(self, client: Any, query: str, k: int = 3) -> Any:
        method = getattr(client, "search", None) or getattr(client, "retrieve", None)
        if not callable(method):
            raise RuntimeError("Mneno MemoryClient does not expose search/retrieve.")
        try:
            return method(query=query, limit=k)
        except TypeError:
            return method(query, k=k)

    def _load_module(self) -> Any:
        if self._module is not None:
            return self._module
        try:
            self._module = importlib.import_module(self.module_name)
        except ImportError as exc:
            raise MnenoNotInstalledError(INSTALL_MESSAGE) from exc
        return self._module

    def _resolve_attribute(self, name: str) -> Any | None:
        module = self._load_module()
        direct = getattr(module, name, None)
        if direct is not None:
            return direct
        for child_name in ("evaluation", "benchmark", "exports", "trace", "tracing"):
            child = getattr(module, child_name, None)
            if child is None:
                try:
                    child = importlib.import_module(f"{self.module_name}.{child_name}")
                except ImportError:
                    continue
            value = getattr(child, name, None)
            if value is not None:
                return value
        return None

    def _call_sdk(self, name: str, *args: Any, **kwargs: Any) -> Any:
        client = kwargs.get("client")
        client_method = getattr(client, name, None) if client is not None else None
        function = (
            client_method if callable(client_method) else self._resolve_attribute(name)
        )
        if not callable(function):
            raise RuntimeError(f"The installed Mneno SDK does not expose {name}().")
        if client_method is function:
            kwargs = {key: value for key, value in kwargs.items() if key != "client"}
        return _invoke(cast(Callable[..., Any], function), args, kwargs)


def is_mneno_available() -> bool:
    return MnenoAdapter().is_available()


def create_memory_client(**kwargs: Any) -> Any:
    return MnenoAdapter().create_client(**kwargs)


def retrieve_with_mneno(
    memories: list[dict[str, Any]], query: str, k: int = 3
) -> list[str]:
    """Backward-compatible retrieval helper implemented through MnenoAdapter."""

    adapter = MnenoAdapter()
    client = adapter.create_client()
    for memory in memories:
        adapter.add_memory(client, memory)
    raw_results = adapter.search(client, query, k)
    return _extract_memory_ids(raw_results)[:k]


def _extract_memory_ids(raw_results: Any) -> list[str]:
    if isinstance(raw_results, dict):
        raw_results = raw_results.get("results", raw_results.get("memories", []))
    if not isinstance(raw_results, Iterable) or isinstance(raw_results, (str, bytes)):
        raise RuntimeError("Mneno retrieval returned an unsupported result shape.")

    memory_ids: list[str] = []
    for item in raw_results:
        if isinstance(item, str):
            memory_ids.append(item)
        elif isinstance(item, dict):
            value = item.get("id") or item.get("memory_id")
            if value is not None:
                memory_ids.append(str(value))
        else:
            value = getattr(item, "id", None) or getattr(item, "memory_id", None)
            if value is not None:
                memory_ids.append(str(value))
    return memory_ids


def _invoke(
    function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    """Pass supported keywords while retaining compatibility with **kwargs APIs."""

    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return function(*args, **kwargs)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return function(*args, **kwargs)
    supported = {
        key: value for key, value in kwargs.items() if key in signature.parameters
    }
    return function(*args, **supported)


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _extract_metrics(value: Any) -> dict[str, float | int | None]:
    metrics = _value(value, "metrics", {})
    if hasattr(metrics, "model_dump"):
        metrics = metrics.model_dump(mode="json")
    if not isinstance(metrics, Mapping):
        return {}
    normalized: dict[str, float | int | None] = {}
    for key, item in metrics.items():
        metric_value = _value(item, "value", item)
        if metric_value is None or (
            isinstance(metric_value, (int, float))
            and not isinstance(metric_value, bool)
        ):
            normalized[str(key)] = metric_value
    return normalized


def _extract_trace_id(value: Any) -> str | None:
    trace_id = _value(value, "trace_id")
    if trace_id is None:
        trace = _value(value, "trace")
        trace_id = _value(trace, "id") or _value(trace, "trace_id")
    return str(trace_id) if trace_id is not None else None


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: _to_jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value
