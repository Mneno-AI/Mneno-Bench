from benchmarks.mneno_suite.trace_analysis import (
    extract_conflict_events,
    extract_exclusion_reasons,
    extract_hierarchy_events,
    extract_inclusion_reasons,
    extract_memory_decisions,
)


def test_trace_analysis_extracts_reasons_and_events() -> None:
    trace = {
        "format": "mneno.trace",
        "version": 1,
        "trace": {
            "events": [
                {
                    "event_type": "memory_included",
                    "data": {"memory_id": "m1", "reason": "current preference"},
                },
                {
                    "event_type": "memory_suppressed",
                    "data": {"memory_id": "m2", "reason": "superseded"},
                },
                {"event_type": "conflict_resolved", "memory_id": "m1"},
                {"event_type": "hierarchy_promoted", "memory_id": "m1"},
            ]
        },
    }

    assert extract_inclusion_reasons(trace) == {"m1": ["current preference"]}
    assert extract_exclusion_reasons(trace) == {"m2": ["superseded"]}
    assert len(extract_memory_decisions(trace)) == 2
    assert len(extract_conflict_events(trace)) == 1
    assert len(extract_hierarchy_events(trace)) == 1


def test_trace_analysis_handles_unknown_shape() -> None:
    assert extract_memory_decisions(None) == []
    assert extract_inclusion_reasons({"unknown": "shape"}) == {}
    assert extract_exclusion_reasons(["not", "a", "trace"]) == {}
