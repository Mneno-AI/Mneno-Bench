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
        return [
            self.load_trace_export(path)
            for path in sorted(Path(directory).glob("*.json"))
        ]

    def _summarize(self, trace: dict[str, Any]) -> TraceSummary:
        operations = _items(trace, "operations")
        events = _items(trace, "events")
        decisions = _items(trace, "decisions")
        trace_id = trace.get("id") or trace.get("trace_id")
        return TraceSummary(
            trace_id=str(trace_id) if trace_id is not None else None,
            operation_count=len(operations),
            event_count=len(events),
            decision_count=len(decisions),
            duration_ms=_duration_ms(trace),
            retrieved_memory_ids=_string_list(trace, "retrieved_memory_ids"),
            selected_memory_ids=_string_list(trace, "selected_memory_ids"),
            suppressed_memory_ids=_string_list(trace, "suppressed_memory_ids"),
            conflict_resolutions=_string_list(trace, "conflict_resolutions"),
            lifecycle_events=_string_list(trace, "lifecycle_events"),
            explanations=_string_list(trace, "explanations"),
            explainability_coverage=_optional_float(
                trace.get("explainability_coverage")
            ),
            raw_trace_reference=_optional_string(trace.get("raw_trace_reference")),
        )


def _items(trace: dict[str, Any], key: str) -> list[Any]:
    value = trace.get(key, [])
    return value if isinstance(value, list) else []


def _string_list(trace: dict[str, Any], key: str) -> list[str]:
    return [str(item) for item in _items(trace, key)]


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
