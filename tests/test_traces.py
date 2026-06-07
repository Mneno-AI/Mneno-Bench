from pathlib import Path

import pytest

from benchmarks.common.traces import TraceLoader
from benchmarks.common.utils import save_json


def test_trace_loader_validates_and_summarizes_v1(tmp_path: Path) -> None:
    export = {
        "format": "mneno.trace",
        "version": 1,
        "trace": {
            "id": "trace-1",
            "operations": [{}, {}],
            "events": [{}],
            "decisions": [{}, {}, {}],
            "duration_ms": 12.5,
            "suppressed_memory_ids": ["stale"],
        },
    }
    path = save_json(tmp_path / "trace.json", export)

    summary = TraceLoader().load_trace_export(path)

    assert summary.trace_id == "trace-1"
    assert summary.operation_count == 2
    assert summary.event_count == 1
    assert summary.decision_count == 3
    assert summary.duration_ms == 12.5
    assert summary.suppressed_memory_ids == ["stale"]


def test_trace_loader_rejects_format_and_version() -> None:
    loader = TraceLoader()

    with pytest.raises(ValueError, match="format"):
        loader.load_trace_export({"format": "other", "version": 1, "trace": {}})
    with pytest.raises(ValueError, match="Unsupported"):
        loader.load_trace_export({"format": "mneno.trace", "version": 2, "trace": {}})
