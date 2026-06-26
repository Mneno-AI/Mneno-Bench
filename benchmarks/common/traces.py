"""Validation and summarization for Mneno trace v1 exports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from benchmarks.common.schema import TraceSummary
from benchmarks.common.utils import load_json


class TraceExport(BaseModel):
    """Validated mneno.trace v1 envelope."""

    model_config = ConfigDict(extra="allow")

    format: str
    version: int
    trace: dict[str, Any]


class TraceLoader:
    """Load individual trace objects, exports, or directories of exports."""

    def load_trace(self, source: str | Path | dict[str, Any]) -> TraceSummary:
        payload = load_json(source) if isinstance(source, (str, Path)) else source
        if payload.get("format") == "mneno.trace":
            return self.load_trace_export(payload)
        return self._summarize(dict(payload))

    def load_trace_export(self, source: str | Path | dict[str, Any]) -> TraceSummary:
        payload = load_json(source) if isinstance(source, (str, Path)) else source
        export = TraceExport.model_validate(payload)
        if export.format != "mneno.trace":
            raise ValueError("Trace export format must be 'mneno.trace'.")
        if export.version != 1:
            raise ValueError(f"Unsupported mneno.trace version: {export.version}")
        return self._summarize(export.trace)

    def load_trace_directory(self, directory: str | Path) -> list[TraceSummary]:
        paths = [
            *Path(directory).glob("*.json"),
            *Path(directory).glob("*.json.gz"),
        ]
        return [self.load_trace_export(path) for path in sorted(paths)]

    def _summarize(self, trace: dict[str, Any]) -> TraceSummary:
        operations = _items(trace, "operations")
        events = _items(trace, "events")
        decisions = _items(trace, "decisions")
        if not operations and trace.get("operation") is not None:
            operations = [trace["operation"]]
        if not decisions:
            decisions = [event for event in events if _is_decision_event(event)]
        trace_id = trace.get("id") or trace.get("trace_id")
        identity_map = _event_identity_map(events)
        retrieved_ids = _mapped_string_list(
            trace, "retrieved_memory_ids", identity_map
        )
        selected_ids = _unique_strings(
            [
                *_mapped_string_list(trace, "selected_memory_ids", identity_map),
                *_event_ids(events, "final_results_selected", identity_map),
                *_event_ids(events, "retrieval_candidate_decision", identity_map),
            ]
        )
        included_ids = _unique_strings(
            [
                *_mapped_string_list(trace, "included_memory_ids", identity_map),
                *_event_ids(events, "context_item_included", identity_map),
            ]
        )
        excluded_ids = _unique_strings(
            [
                *_mapped_string_list(trace, "excluded_memory_ids", identity_map),
                *_event_ids(events, "context_item_excluded", identity_map),
            ]
        )
        return TraceSummary(
            trace_id=str(trace_id) if trace_id is not None else None,
            operation_count=len(operations),
            event_count=len(events),
            decision_count=len(decisions),
            duration_ms=_duration_ms(trace),
            retrieved_memory_ids=_unique_strings([*retrieved_ids, *selected_ids]),
            selected_memory_ids=selected_ids,
            included_memory_ids=included_ids,
            excluded_memory_ids=excluded_ids,
            suppressed_memory_ids=_mapped_string_list(
                trace, "suppressed_memory_ids", identity_map
            ),
            conflict_resolutions=_plain_string_list(trace, "conflict_resolutions"),
            lifecycle_events=_plain_string_list(trace, "lifecycle_events"),
            explanations=_plain_string_list(trace, "explanations"),
            explainability_coverage=_optional_float(
                trace.get("explainability_coverage")
            ),
            raw_trace_reference=_optional_string(trace.get("raw_trace_reference")),
        )


def _items(trace: dict[str, Any], key: str) -> list[Any]:
    value = trace.get(key, [])
    return value if isinstance(value, list) else []


def _is_decision_event(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    event_type = str(value.get("event_type", "")).lower()
    return any(
        term in event_type
        for term in ("decision", "included", "excluded", "selected", "suppressed")
    )


def _mapped_string_list(
    trace: dict[str, Any], key: str, identity_map: dict[str, str]
) -> list[str]:
    return [_map_id(item, identity_map) for item in _items(trace, key)]


def _plain_string_list(trace: dict[str, Any], key: str) -> list[str]:
    return [str(item) for item in _items(trace, key)]


def _event_identity_map(events: list[Any]) -> dict[str, str]:
    identities: dict[str, str] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        internal_id = (
            data.get("internal_memory_id")
            or data.get("memory_id")
            or event.get("memory_id")
        )
        dataset_id = data.get("dataset_memory_id")
        if internal_id is not None and dataset_id is not None:
            identities[str(internal_id)] = str(dataset_id)
    return identities


def _event_ids(
    events: list[Any], event_type: str, identity_map: dict[str, str]
) -> list[str]:
    ids: list[str] = []
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != event_type:
            continue
        raw_data = event.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        if event_type == "final_results_selected":
            ids.extend(
                _map_id(item, identity_map)
                for item in data.get("memory_ids", [])
                if item is not None
            )
            continue
        if event_type == "retrieval_candidate_decision" and not data.get("included"):
            continue
        memory_id = (
            data.get("dataset_memory_id")
            or data.get("internal_memory_id")
            or data.get("memory_id")
            or event.get("memory_id")
        )
        if memory_id is not None:
            ids.append(_map_id(memory_id, identity_map))
    return _unique_strings(ids)


def _map_id(value: Any, identity_map: dict[str, str]) -> str:
    item = str(value)
    return identity_map.get(item, item)


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _duration_ms(trace: dict[str, Any]) -> float | None:
    for key in ("duration_ms", "duration"):
        value = trace.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    started = trace.get("started_at") or trace.get("start_time")
    finished = trace.get("finished_at") or trace.get("end_time")
    if not isinstance(started, str) or not isinstance(finished, str):
        return None
    try:
        start_time = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((end_time - start_time).total_seconds() * 1000, 4)
