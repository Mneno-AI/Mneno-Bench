from pathlib import Path

import pytest

from benchmarks.common.traces import TraceLoader
from benchmarks.common.utils import load_json, save_json


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


def test_trace_loader_reads_gzipped_trace_exports(tmp_path: Path) -> None:
    export = {
        "format": "mneno.trace",
        "version": 1,
        "trace": {"id": "trace-gzip", "events": [{"event_type": "decision"}]},
    }
    path = save_json(tmp_path / "trace.json.gz", export)

    assert load_json(path)["trace"]["id"] == "trace-gzip"
    summary = TraceLoader().load_trace_export(path)

    assert summary.trace_id == "trace-gzip"
    assert summary.decision_count == 1


def test_trace_loader_rejects_format_and_version() -> None:
    loader = TraceLoader()

    with pytest.raises(ValueError, match="format"):
        loader.load_trace_export({"format": "other", "version": 1, "trace": {}})
    with pytest.raises(ValueError, match="Unsupported"):
        loader.load_trace_export({"format": "mneno.trace", "version": 2, "trace": {}})


def test_trace_loader_derives_dataset_ids_from_events() -> None:
    summary = TraceLoader().load_trace_export(
        {
            "format": "mneno.trace",
            "version": 1,
            "trace": {
                "id": "trace-events",
                "events": [
                    {
                        "event_type": "retrieval_candidate_decision",
                        "memory_id": "uuid-1",
                        "data": {
                            "internal_memory_id": "uuid-1",
                            "dataset_memory_id": "D1:3",
                            "included": True,
                        },
                    },
                    {
                        "event_type": "final_results_selected",
                        "data": {"memory_ids": ["uuid-1"]},
                    },
                    {
                        "event_type": "context_item_included",
                        "memory_id": "uuid-1",
                        "data": {
                            "internal_memory_id": "uuid-1",
                            "dataset_memory_id": "D1:3",
                        },
                    },
                    {
                        "event_type": "context_item_excluded",
                        "memory_id": "uuid-2",
                        "data": {
                            "internal_memory_id": "uuid-2",
                            "dataset_memory_id": "D1:4",
                        },
                    },
                ],
            },
        }
    )

    assert summary.retrieved_memory_ids == ["D1:3"]
    assert summary.selected_memory_ids == ["D1:3"]
    assert summary.included_memory_ids == ["D1:3"]
    assert summary.excluded_memory_ids == ["D1:4"]
    assert summary.suppressed_memory_ids == []


def test_trace_loader_preserves_top_level_id_arrays() -> None:
    summary = TraceLoader().load_trace(
        {
            "id": "legacy-trace",
            "retrieved_memory_ids": ["retrieved"],
            "selected_memory_ids": ["selected"],
            "included_memory_ids": ["included"],
            "excluded_memory_ids": ["excluded"],
            "suppressed_memory_ids": ["suppressed"],
        }
    )

    assert summary.retrieved_memory_ids == ["retrieved", "selected"]
    assert summary.selected_memory_ids == ["selected"]
    assert summary.included_memory_ids == ["included"]
    assert summary.excluded_memory_ids == ["excluded"]
    assert summary.suppressed_memory_ids == ["suppressed"]
