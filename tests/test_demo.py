from pathlib import Path
from typing import Any

from benchmarks.common.schema import (
    NormalizedCompactionResult,
    NormalizedContextResult,
    NormalizedSearchResult,
    RunStatus,
)
from benchmarks.mneno_suite.run import PROJECT_ROOT, run_demo


class MissingMnenoAdapter:
    def is_available(self) -> bool:
        return False


def test_demo_writes_json_and_report_without_mneno(tmp_path: Path) -> None:
    run = run_demo(
        PROJECT_ROOT / "data",
        tmp_path,
        adapter=MissingMnenoAdapter(),  # type: ignore[arg-type]
    )

    assert run.status == RunStatus.COMPLETED
    assert len(run.results) == 24
    assert run.systems == [
        "keyword_baseline",
        "full_context_baseline",
        "random_baseline",
        "mneno",
    ]
    assert all(
        result.mneno_result is not None
        and result.mneno_result.status == RunStatus.SKIPPED
        for result in run.results
    )
    assert (tmp_path / "mneno" / "context_rot_suite_latest.json").exists()
    assert (tmp_path / "reports" / "context_rot_suite_latest.md").exists()
    summary = run.export_metadata["context_rot_suite"]
    assert summary["systems"]["mneno"]["status"] == "skipped"
    assert summary["systems"]["mneno"]["context_rot_score"] is None
    assert summary["systems"]["full_context_baseline"]["context_rot_score"] is not None


def test_suite_summary_is_deterministic_when_run_metadata_is_ignored(
    tmp_path: Path,
) -> None:
    adapter = MissingMnenoAdapter()
    first = run_demo(
        PROJECT_ROOT / "data",
        tmp_path,
        adapter=adapter,  # type: ignore[arg-type]
    )
    second = run_demo(
        PROJECT_ROOT / "data",
        tmp_path,
        adapter=adapter,  # type: ignore[arg-type]
    )

    assert (
        first.export_metadata["context_rot_suite"]
        == second.export_metadata["context_rot_suite"]
    )


class FakeMnenoAdapter:
    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return "0.3.1"

    def create_client(self, **kwargs: Any) -> dict[str, Any]:
        return {"config": kwargs, "memories": []}

    def add_memory(self, client: dict[str, Any], memory: dict[str, Any]) -> None:
        client["memories"].append(memory)

    def evaluate_search(self, **kwargs: Any) -> NormalizedSearchResult:
        expected = kwargs["expected_memory_ids"]
        return NormalizedSearchResult(
            provider="mneno",
            query=kwargs["query"],
            metrics={"precision": 1.0, "latency_ms": 1.0},
            trace_id=f"trace-{expected[0]}",
            raw_result={"retrieved_memory_ids": expected},
        )

    def evaluate_context(self, **kwargs: Any) -> NormalizedContextResult:
        return NormalizedContextResult(
            provider="mneno",
            query=kwargs["query"],
            metrics={"context_efficiency_ratio": 1.0},
        )

    def evaluate_compaction(self, **kwargs: Any) -> NormalizedCompactionResult:
        return NormalizedCompactionResult(
            provider="mneno",
            metrics={"retention": 1.0},
        )

    def export_trace(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "format": "mneno.trace",
            "version": 1,
            "trace": {
                "id": kwargs["trace_id"],
                "operations": [{}],
                "events": [{}],
                "decisions": [{}],
            },
        }

    def export_all_traces(self, **kwargs: Any) -> dict[str, Any]:
        return {"format": "mneno.trace.collection", "version": 1, "traces": []}

    def export_benchmark(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "format": "mneno.benchmark.result",
            "version": 1,
            "result": kwargs["result"],
        }


def test_demo_consumes_installed_mneno_exports(tmp_path: Path) -> None:
    run = run_demo(
        PROJECT_ROOT / "data",
        tmp_path,
        adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
    )

    assert run.status == RunStatus.COMPLETED
    assert run.mneno_version == "0.3.1"
    assert all(
        result.mneno_result is not None
        and result.mneno_result.status == RunStatus.COMPLETED
        and result.mneno_result.trace_summary is not None
        for result in run.results
    )
    assert len(run.results) == 24
    assert len(list((tmp_path / "mneno" / "exports").glob("*.json"))) == 24
    assert len(list((tmp_path / "mneno" / "traces").glob("*.json"))) == 25
    summary = run.export_metadata["context_rot_suite"]
    assert summary["systems"]["mneno"]["status"] == "completed"
    assert summary["systems"]["mneno"]["context_rot_score"] is not None
