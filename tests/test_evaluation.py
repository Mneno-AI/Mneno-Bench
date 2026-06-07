import pytest

from benchmarks.common.evaluation import EvaluationLoader
from benchmarks.common.schema import RunStatus


def test_evaluation_loader_converts_v1_export() -> None:
    payload = {
        "format": "mneno.benchmark.result",
        "version": 1,
        "run_id": "core-run",
        "benchmark": "search",
        "mneno_version": "0.3.2",
        "timestamp": "2026-06-07T12:00:00Z",
        "results": [
            {
                "case_id": "case-1",
                "query": "What is current?",
                "expected_memory_ids": ["active"],
                "result": {
                    "status": "completed",
                    "retrieved_memory_ids": ["active"],
                    "context_tokens": 10,
                    "latency_ms": 3.0,
                },
                "metrics": {"mneno": {"precision": 1.0}},
            }
        ],
    }

    run, results = EvaluationLoader().load(payload)

    assert run.run_id == "core-run"
    assert run.status == RunStatus.COMPLETED
    assert run.mneno_version == "0.3.2"
    assert results[0].mneno_result is not None
    assert results[0].mneno_result.retrieved_memory_ids == ["active"]
    assert results[0].metrics["mneno"][0].value == 1.0
    assert run.export_metadata["raw_benchmark_export"] == payload


def test_evaluation_loader_rejects_invalid_exports() -> None:
    loader = EvaluationLoader()

    with pytest.raises(ValueError, match="format"):
        loader.load({"format": "other", "version": 1})
    with pytest.raises(ValueError, match="Unsupported"):
        loader.load({"format": "mneno.benchmark.result", "version": 2})
