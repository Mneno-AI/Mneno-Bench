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

    def supports(self, name: str, client: Any | None = None) -> bool:
        del client
        return name in {
            "evaluate_search",
            "evaluate_context",
            "evaluate_compaction",
            "export_trace",
            "export_all_traces",
        }

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
    execution = run.export_metadata["mneno_execution"]
    assert execution["capability_report"]["partial"]
    assert not execution["hierarchy_evaluated"]
    assert not execution["compaction_previewed"]
    assert summary["systems"]["mneno"]["metrics"]["lifecycle_alignment_score"] is None


class FullMnenoAdapter(FakeMnenoAdapter):
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self.internal_ids: list[str] = []

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def supports(self, name: str, client: Any | None = None) -> bool:
        del client
        return name in {
            "add_with_report",
            "evaluate_search",
            "evaluate_context",
            "evaluate_compaction",
            "build_context",
            "create_session",
            "evaluate_hierarchy",
            "preview_compaction",
            "export_trace",
            "export_all_traces",
        }

    def create_session(self, **kwargs: Any) -> dict[str, Any]:
        self._called("create_session")
        return {"id": kwargs["session_id"]}

    def add_with_report(
        self, client: dict[str, Any], memory: dict[str, Any]
    ) -> dict[str, Any]:
        self._called("add_with_report")
        internal_id = f"internal-{memory['id']}"
        self.internal_ids.append(internal_id)
        client["memories"].append(memory)
        conflicts = [{}] if memory["id"] == "sp-python-new" else []
        return {
            "memory_id": internal_id,
            "conflicts": conflicts,
            "resolution_actions": ["supersede"] if conflicts else [],
            "trace_id": f"add-{memory['id']}",
        }

    def evaluate_hierarchy(self, **kwargs: Any) -> dict[str, Any]:
        self._called("evaluate_hierarchy")
        return {"promoted": ["x"], "archived": ["y"], "trace_id": "hierarchy"}

    def preview_compaction(self, **kwargs: Any) -> dict[str, Any]:
        self._called("preview_compaction")
        return {
            "kept_ids": self.internal_ids,
            "kept": len(self.internal_ids),
            "merged": 2,
            "discarded": 1,
            "trace_id": "compaction",
        }

    def evaluate_search(self, **kwargs: Any) -> NormalizedSearchResult:
        self._called("evaluate_search")
        expected = kwargs["expected_memory_ids"]
        return NormalizedSearchResult(
            provider="mneno",
            query=kwargs["query"],
            metrics={"latency_ms": 1.0},
            trace_id=f"search-{expected[0]}",
            raw_result={"retrieved_memory_ids": expected},
        )

    def evaluate_context(self, **kwargs: Any) -> NormalizedContextResult:
        self._called("evaluate_context")
        return NormalizedContextResult(
            provider="mneno", query=kwargs["query"], metrics={}
        )

    def build_context(self, **kwargs: Any) -> dict[str, Any]:
        self._called("build_context")
        return {
            "included_memory_ids": kwargs["expected_memory_ids"],
            "excluded_memory_ids": kwargs["forbidden_memory_ids"],
            "trace_id": f"context-{kwargs['expected_memory_ids'][0]}",
        }

    def evaluate_compaction(self, **kwargs: Any) -> NormalizedCompactionResult:
        self._called("evaluate_compaction")
        return NormalizedCompactionResult(provider="mneno", metrics={})

    def export_trace(self, **kwargs: Any) -> dict[str, Any]:
        trace_id = kwargs["trace_id"]
        memory_id = trace_id.split("-", 1)[-1]
        return {
            "format": "mneno.trace",
            "version": 1,
            "trace": {
                "id": trace_id,
                "events": [
                    {
                        "event_type": "memory_included",
                        "data": {"memory_id": memory_id, "reason": "active"},
                    }
                ],
                "decisions": [{}],
            },
        }


def test_full_mneno_execution_uses_runtime_capabilities(tmp_path: Path) -> None:
    adapter = FullMnenoAdapter()
    run = run_demo(
        PROJECT_ROOT / "data",
        tmp_path,
        adapter=adapter,  # type: ignore[arg-type]
    )

    execution = run.export_metadata["mneno_execution"]
    assert execution["sessions_created"] == 12
    assert execution["memories_loaded"] == 48
    assert execution["conflicts_detected"] == 1
    assert execution["hierarchy_evaluated"]
    assert execution["hierarchy_transitions"] == {"archived": 1, "promoted": 1}
    assert execution["compaction_previewed"]
    assert execution["compaction_stats"]["kept"] == 48
    assert execution["memory_id_map"]["sp-python-new"] == "internal-sp-python-new"
    python_load = next(
        item
        for item in execution["memory_loads"]
        if item["dataset_memory_id"] == "sp-python-new"
    )
    assert python_load["mneno_memory_id"] == "internal-sp-python-new"
    assert python_load["conflict_reports"] == [{}]
    assert python_load["resolution_actions"] == ["supersede"]
    assert python_load["trace_ids"] == ["add-sp-python-new"]
    assert adapter.calls["create_session"] == 12
    assert adapter.calls["add_with_report"] == 48
    assert adapter.calls["evaluate_hierarchy"] == 1
    assert adapter.calls["preview_compaction"] == 1
    assert adapter.calls["build_context"] == 24
    first = run.results[0].mneno_result
    assert first is not None
    assert first.included_memory_ids == ["sp-python-new"]
    assert first.excluded_memory_ids == ["sp-python-old"]
    assert first.decision_summary is not None
    assert first.decision_summary.inclusion_reasons
