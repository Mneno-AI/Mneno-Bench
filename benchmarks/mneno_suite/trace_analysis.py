"""Best-effort extraction of stable decisions from Mneno trace exports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def extract_memory_decisions(trace_export: Any) -> list[dict[str, Any]]:
    return [event for event in _events(trace_export) if _is_decision(event)]


def extract_inclusion_reasons(trace_export: Any) -> dict[str, list[str]]:
    return _reasons(trace_export, include=True)


def extract_exclusion_reasons(trace_export: Any) -> dict[str, list[str]]:
    return _reasons(trace_export, include=False)


def extract_conflict_events(trace_export: Any) -> list[dict[str, Any]]:
    return _matching_events(trace_export, ("conflict", "contradiction", "supersed"))


def extract_hierarchy_events(trace_export: Any) -> list[dict[str, Any]]:
    return _matching_events(
        trace_export, ("hierarchy", "promot", "demot", "archive", "layer")
    )


def extract_session_events(trace_export: Any) -> list[dict[str, Any]]:
    return _matching_events(trace_export, ("session",))


def _events(trace_export: Any) -> list[dict[str, Any]]:
    if not isinstance(trace_export, Mapping):
        return []
    trace = trace_export.get("trace", trace_export)
    candidates: list[dict[str, Any]] = []
    _collect_events(trace, candidates)
    return candidates


def _collect_events(value: Any, output: list[dict[str, Any]]) -> None:
    if isinstance(value, Mapping):
        event_type = value.get("event_type") or value.get("type") or value.get("name")
        if event_type is not None:
            output.append({str(key): item for key, item in value.items()})
        for key, item in value.items():
            if key in {"events", "decisions", "operations", "children", "data"}:
                _collect_events(item, output)
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for item in value:
            _collect_events(item, output)


def _event_text(event: Mapping[str, Any]) -> str:
    fields = (
        event.get("event_type"),
        event.get("type"),
        event.get("name"),
        event.get("action"),
        event.get("decision"),
        event.get("reason"),
        event.get("status"),
    )
    return " ".join(str(value).lower() for value in fields if value is not None)


def _matching_events(trace_export: Any, terms: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        event
        for event in _events(trace_export)
        if any(term in _event_text(event) for term in terms)
    ]


def _is_decision(event: Mapping[str, Any]) -> bool:
    text = _event_text(event)
    return any(
        term in text
        for term in ("decision", "include", "exclude", "select", "suppress")
    )


def _reasons(trace_export: Any, include: bool) -> dict[str, list[str]]:
    output: defaultdict[str, list[str]] = defaultdict(list)
    terms = (
        ("include", "select", "keep")
        if include
        else ("exclude", "suppress", "discard", "reject")
    )
    for event in _events(trace_export):
        if not any(term in _event_text(event) for term in terms):
            continue
        memory_id = _memory_id(event)
        reason = _reason(event)
        if memory_id and reason and reason not in output[memory_id]:
            output[memory_id].append(reason)
    return dict(output)


def _memory_id(event: Mapping[str, Any]) -> str | None:
    raw_data = event.get("data")
    data: Mapping[str, Any] = raw_data if isinstance(raw_data, Mapping) else {}
    for source in (event, data):
        value = (
            source.get("dataset_memory_id")
            or source.get("memory_id")
            or source.get("id")
        )
        if value is not None:
            return str(value)
    return None


def _reason(event: Mapping[str, Any]) -> str | None:
    raw_data = event.get("data")
    data: Mapping[str, Any] = raw_data if isinstance(raw_data, Mapping) else {}
    for source in (event, data):
        value = (
            source.get("reason") or source.get("explanation") or source.get("message")
        )
        if value is not None:
            return str(value)
    return None
