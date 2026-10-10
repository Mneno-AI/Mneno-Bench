import json
from pathlib import Path
from threading import Event
from typing import Any

from benchmarks.common.schema import (
    NormalizedContextResult,
    NormalizedSearchResult,
    RunStatus,
)
from benchmarks.locomo.config import LOCOMOEvaluationConfig
from benchmarks.locomo.run import (
    _CaseProgress,
    _EnterStatusPrinter,
    _context_ids,
    _extract_ids,
    _format_duration,
    _internal_memory_id,
    _normalize_ids,
    _should_report_progress,
    run_locomo,
)


def _write_dataset(data_dir: Path) -> None:
    raw = data_dir / "locomo" / "raw"
    raw.mkdir(parents=True)
    payload = [
        {
            "sample_id": "conv-test",
            "conversation": {
                "speaker_a": "Alex",
                "speaker_b": "Blair",
                "session_1_date_time": "10:00 am on 1 January, 2024",
                "session_1": [
                    {
                        "speaker": "Alex",
                        "dia_id": "D1:1",
                        "text": "I moved to Rome.",
                    },
                    {
                        "speaker": "Blair",
                        "dia_id": "D1:2",
                        "text": "How is Rome?",
                    },
                ],
            },
            "qa": [
                {
                    "question": "Where did Alex move?",
                    "answer": "Rome",
                    "category": 1,
                    "evidence": ["D1:1"],
                }
            ],
        }
    ]
    (raw / "locomo10.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_two_conversation_dataset(data_dir: Path) -> None:
    _write_dataset(data_dir)
    path = data_dir / "locomo" / "raw" / "locomo10.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    second = json.loads(json.dumps(payload[0]))
    second["sample_id"] = "conv-test-2"
    second["conversation"]["session_1"][0]["text"] = "I moved to Milan."
    second["qa"][0]["answer"] = "Milan"
    payload.append(second)
    path.write_text(json.dumps(payload), encoding="utf-8")


class MissingMnenoAdapter:
    def is_available(self) -> bool:
        return False


def test_empty_legacy_fields_do_not_hide_structured_memory_ids() -> None:
    assert _extract_ids({
        "retrieved_memory_ids": [],
        "selected_memory_ids": ["uuid-evidence"],
    }) == ["uuid-evidence"]
    for kind in ("included", "excluded"):
        ids = _context_ids({
            f"{kind}_memory_ids": [],
            kind: [{"memory_id": "uuid-evidence"}],
        }, kind)
        assert _normalize_ids(ids, {"uuid-evidence": "D1:1"}) == ["D1:1"]
    assert _normalize_ids(["unknown-uuid"], {}) == ["unknown-uuid"]


class FakeMnenoAdapter:
    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return "0.test"

    def create_client(self, **kwargs: Any) -> dict[str, Any]:
        return {"config": kwargs, "memories": []}

    def supports(self, name: str, client: Any | None = None) -> bool:
        del client
        return name in {
            "evaluate_search",
            "evaluate_context",
            "build_context",
            "export_trace",
        }

    def add_memory(
        self, client: dict[str, Any], memory: dict[str, Any]
    ) -> dict[str, str]:
        client["memories"].append(memory)
        return {"memory_id": memory["id"]}

    def evaluate_search(self, **kwargs: Any) -> NormalizedSearchResult:
        evidence = kwargs["expected_memory_ids"]
        return NormalizedSearchResult(
            provider="mneno",
            query=kwargs["query"],
            metrics={"latency_ms": 1.0},
            trace_id="search-trace",
            raw_result={"retrieved_memory_ids": evidence},
        )

    def evaluate_context(self, **kwargs: Any) -> NormalizedContextResult:
        return NormalizedContextResult(
            provider="mneno",
            query=kwargs["query"],
            metrics={},
            trace_id="context-trace",
        )

    def build_context(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "included_memory_ids": kwargs["expected_memory_ids"],
            "trace_id": "build-trace",
        }

    def export_trace(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "format": "mneno.trace",
            "version": 1,
            "trace": {"id": kwargs["trace_id"], "events": [{}]},
        }


class RealShapeMnenoAdapter(FakeMnenoAdapter):
    def supports(self, name: str, client: Any | None = None) -> bool:
        return name == "add_with_report" or super().supports(name, client=client)

    def add_with_report(
        self, client: dict[str, Any], memory: dict[str, Any]
    ) -> dict[str, Any]:
        client["memories"].append(memory)
        return {"memory": {"id": f"uuid-{memory['id']}"}}

    def evaluate_search(self, **kwargs: Any) -> NormalizedSearchResult:
        return NormalizedSearchResult(
            provider="mneno",
            query=kwargs["query"],
            metrics={"latency_ms": 1.0},
            trace_id="search-trace",
            raw_result={"selected_memory_ids": ["uuid-D1:1"]},
        )

    def build_context(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "included": [{"memory_id": "uuid-D1:1", "content": "Alex moved to Rome."}],
            "excluded": [{"memory_id": "uuid-D1:2", "content": "How is Rome?"}],
            "trace_id": "build-trace",
        }

    def export_trace(self, **kwargs: Any) -> dict[str, Any]:
        trace_id = kwargs["trace_id"]
        events: list[dict[str, Any]] = []
        if trace_id == "search-trace":
            events = [
                {
                    "event_type": "retrieval_candidate_decision",
                    "memory_id": "uuid-D1:1",
                    "data": {
                        "internal_memory_id": "uuid-D1:1",
                        "dataset_memory_id": "D1:1",
                        "included": True,
                    },
                },
                {
                    "event_type": "final_results_selected",
                    "data": {"memory_ids": ["uuid-D1:1"]},
                },
            ]
        elif trace_id == "build-trace":
            events = [
                {
                    "event_type": "context_item_included",
                    "memory_id": "uuid-D1:1",
                    "data": {"dataset_memory_id": "D1:1"},
                },
                {
                    "event_type": "context_item_excluded",
                    "memory_id": "uuid-D1:2",
                    "data": {"dataset_memory_id": "D1:2"},
                },
            ]
        return {
            "format": "mneno.trace",
            "version": 1,
            "trace": {"id": trace_id, "events": events},
        }


class CapturingMnenoAdapter(FakeMnenoAdapter):
    def __init__(self) -> None:
        self.client_kwargs: dict[str, Any] = {}

    def create_client(self, **kwargs: Any) -> dict[str, Any]:
        self.client_kwargs = kwargs
        return super().create_client(**kwargs)


class FailingSearchMnenoAdapter(FakeMnenoAdapter):
    def evaluate_search(self, **kwargs: Any) -> NormalizedSearchResult:
        del kwargs
        raise Exception("provider failure")


def test_runner_writes_dataset_missing_report(tmp_path: Path) -> None:
    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=MissingMnenoAdapter(),  # type: ignore[arg-type]
    )

    assert run.status == RunStatus.DATASET_MISSING
    assert run.export_metadata["locomo"]["dataset_status"] == "dataset_missing"
    assert (tmp_path / "results" / "locomo" / "locomo_latest.json").exists()
    assert (tmp_path / "results" / "locomo" / "locomo_latest.md").exists()
    assert (
        tmp_path / "results" / "locomo" / "failures" / "locomo_failures_latest.json"
    ).exists()
    assert (tmp_path / "results" / "locomo" / "locomo_failures_latest.md").exists()
    assert (
        tmp_path
        / "results"
        / "locomo"
        / "dashboard"
        / "runs"
        / "locomo_dashboard_latest.json"
    ).exists()
    assert (
        tmp_path
        / "results"
        / "locomo"
        / "dashboard"
        / "failures"
        / "locomo_failures_latest.json"
    ).exists()


def test_runner_executes_baselines_when_dataset_present(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")

    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=MissingMnenoAdapter(),  # type: ignore[arg-type]
    )

    assert run.status == RunStatus.COMPLETED
    assert len(run.results) == 1
    assert len(run.results[0].baseline_results) == 2
    assert run.results[0].mneno_result is not None
    assert run.results[0].mneno_result.status == RunStatus.SKIPPED
    assert run.export_metadata["locomo"]["systems"]["mneno"]["status"] == "skipped"
    assert run.export_metadata["locomo"]["evaluation_mode"] == "retrieval_only"
    assert (
        run.export_metadata["locomo"]["systems"]["keyword_baseline"]["score_labels"][
            "official_score"
        ]
        is None
    )
    retrieval_metrics = {
        metric.name: metric.value for metric in run.summary_metrics["keyword_baseline"]
    }
    assert retrieval_metrics["evidence_recall"] is not None
    assert retrieval_metrics["diagnostic_score"] is None
    assert run.export_metadata["locomo"]["failure_analysis"]["failure_count"] > 0


def test_runner_injects_and_records_optional_mneno_reranker(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")
    adapter = CapturingMnenoAdapter()
    config = LOCOMOEvaluationConfig(
        allow_external_calls=True,
        mneno_reranker_model="nvidia_nim/ranking/nvidia/reranker",
        mneno_reranker_provider="nvidia_nim",
        mneno_reranker_api_key_required=False,
    )

    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=adapter,  # type: ignore[arg-type]
        evaluation_config=config,
    )

    assert adapter.client_kwargs["reranker_provider"].name.startswith("litellm:")
    metadata = run.export_metadata["mneno_reranker"]
    assert metadata["enabled"]
    assert metadata["model"] == "nvidia_nim/ranking/nvidia/reranker"
    assert metadata["stats"]["api_requests"] == 0
    assert run.export_metadata["locomo"]["mneno_reranker"] == metadata


def test_runner_records_mneno_provider_failures_without_crashing(
    tmp_path: Path,
) -> None:
    _write_dataset(tmp_path / "data")

    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=FailingSearchMnenoAdapter(),  # type: ignore[arg-type]
    )

    assert run.status == RunStatus.COMPLETED
    assert run.results[0].mneno_result is not None
    assert run.results[0].mneno_result.status == RunStatus.FAILED
    assert "provider failure" in (run.results[0].mneno_result.error or "")
    system = run.export_metadata["locomo"]["systems"]["mneno"]
    assert system["status"] == "failed"
    assert "provider failure" in system["errors"][0]


def test_parallel_runner_preserves_order_and_metrics(tmp_path: Path) -> None:
    _write_two_conversation_dataset(tmp_path / "data")

    serial = run_locomo(
        tmp_path / "data",
        tmp_path / "serial-results",
        evaluation_config=LOCOMOEvaluationConfig(workers=1),
    )
    parallel = run_locomo(
        tmp_path / "data",
        tmp_path / "parallel-results",
        evaluation_config=LOCOMOEvaluationConfig(workers=2),
    )

    assert [result.case.id for result in parallel.results] == [
        result.case.id for result in serial.results
    ]
    assert parallel.summary_metrics == serial.summary_metrics
    execution = parallel.export_metadata["locomo"]["execution"]
    assert execution["backend"] == "process"
    assert execution["effective_workers"] == 2
    assert not execution["latency_comparable"]


def test_runner_deterministic_answer_mode_labels_scores(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")

    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=MissingMnenoAdapter(),  # type: ignore[arg-type]
        evaluation_config=LOCOMOEvaluationConfig(mode="deterministic_answer"),
    )

    summary = run.export_metadata["locomo"]
    metrics = summary["systems"]["keyword_baseline"]["metrics"]
    assert summary["evaluation_mode"] == "deterministic_answer"
    assert metrics["official_score"] is None
    assert metrics["diagnostic_score"] is not None
    assert metrics["locomo_official_f1_on_candidate"] is not None
    candidate = run.results[0].baseline_results[0].metadata["answer_candidate"]
    assert candidate["metadata"]["generation_method"] == (
        "deterministic_extractive_diagnostic"
    )


def test_runner_llm_judge_mode_skips_without_judge_config(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")

    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=MissingMnenoAdapter(),  # type: ignore[arg-type]
        evaluation_config=LOCOMOEvaluationConfig(mode="llm_judge"),
    )

    summary = run.export_metadata["locomo"]
    assert summary["evaluation_mode"] == "llm_judge"
    judge = summary["systems"]["keyword_baseline"]["judge"]
    assert judge["status"] == "skipped"
    metrics = summary["systems"]["keyword_baseline"]["metrics"]
    assert metrics["official_score"] is None
    assert metrics["judge_score"] is None
    result = run.results[0].baseline_results[0].metadata["judge_result"]
    assert result["status"] == "skipped"


def test_retrieval_report_labels_judge_as_not_requested(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")

    run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=MissingMnenoAdapter(),  # type: ignore[arg-type]
    )

    report = (tmp_path / "results" / "locomo" / "locomo_latest.md").read_text()
    assert "- Model: **not requested**" in report
    assert "- Provider: **not requested**" in report


def test_progress_helpers_format_eta_and_throttle_updates() -> None:
    assert _format_duration(5) == "5s"
    assert _format_duration(65) == "1m 05s"
    assert _format_duration(3665) == "1h 01m 05s"
    assert _should_report_progress(1, 100)
    assert _should_report_progress(10, 100)
    assert _should_report_progress(100, 100)
    assert not _should_report_progress(9, 100)


def test_case_progress_reports_case_level_milestones(monkeypatch: Any) -> None:
    completed: list[int] = []
    monkeypatch.setattr(
        "benchmarks.locomo.run._report_progress",
        lambda count, total, started_at: completed.append(count),
    )
    progress = _CaseProgress(total=25, started_at=0.0)

    for _ in range(25):
        progress.advance()

    assert completed == [1, 10, 20, 25]


def test_enter_status_printer_reports_current_progress(monkeypatch: Any) -> None:
    reported = Event()
    lines = iter(["\n", ""])

    class FakeTTY:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return next(lines, "")

    progress = _CaseProgress(total=5, started_at=0.0, initial_completed=2)
    monkeypatch.setattr("benchmarks.locomo.run.sys.stdin", FakeTTY())
    monkeypatch.setattr(progress, "report_now", reported.set)

    printer = _EnterStatusPrinter(progress)
    printer.start()

    assert reported.wait(timeout=1.0)
    printer.stop()


def test_result_id_extraction_preserves_legacy_shapes() -> None:
    for key in (
        "retrieved_memory_ids",
        "selected_memory_ids",
        "memory_ids",
        "included_memory_ids",
        "results",
        "memories",
        "ids",
    ):
        assert _extract_ids({key: [{"memory_id": "uuid-1"}]}) == ["uuid-1"]


def test_context_id_extraction_supports_legacy_and_object_list_shapes() -> None:
    assert _context_ids({"included_memory_ids": ["uuid-1"]}, "included") == ["uuid-1"]
    assert _context_ids({"included": [{"memory_id": "uuid-1"}]}, "included") == [
        "uuid-1"
    ]
    assert _context_ids({"excluded": [{"memory_id": "uuid-2"}]}, "excluded") == [
        "uuid-2"
    ]


def test_selected_uuid_normalizes_to_locomo_evidence_id() -> None:
    raw_ids = _extract_ids({"selected_memory_ids": ["uuid-evidence"]})

    assert _normalize_ids(raw_ids, {"uuid-evidence": "D1:3"}) == ["D1:3"]


def test_internal_memory_id_supports_real_add_with_report_shape() -> None:
    assert _internal_memory_id({"memory": {"id": "uuid-evidence"}}) == ("uuid-evidence")


def test_runner_executes_available_mneno_and_preserves_traces(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")

    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
    )

    result = run.results[0].mneno_result
    assert result is not None
    assert result.status == RunStatus.COMPLETED
    assert result.retrieved_memory_ids == ["D1:1"]
    assert result.included_memory_ids == ["D1:1"]
    assert len(result.trace_ids) == 3
    assert len(list((tmp_path / "results" / "locomo" / "traces").glob("*.json.gz"))) == 3
    assert len(list((tmp_path / "results" / "locomo" / "raw").rglob("*.json"))) == 1


def test_runner_normalizes_real_sdk_result_shapes_to_locomo_ids(
    tmp_path: Path,
) -> None:
    _write_dataset(tmp_path / "data")

    run = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=RealShapeMnenoAdapter(),  # type: ignore[arg-type]
    )

    result = run.results[0].mneno_result
    assert result is not None
    assert result.retrieved_memory_ids == ["D1:1"]
    assert result.included_memory_ids == ["D1:1"]
    assert result.excluded_memory_ids == ["D1:2"]
    assert result.trace_summary is not None
    assert result.trace_summary.retrieved_memory_ids == ["D1:1"]
    assert result.trace_summary.included_memory_ids == ["D1:1"]
    assert result.trace_summary.excluded_memory_ids == ["D1:2"]
    metrics = {metric.name: metric.value for metric in run.results[0].metrics["mneno"]}
    assert metrics["evidence_recall"] == 1.0

    raw_path = Path(str(result.metadata["raw_output_path"]))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert raw["retrieved_dialog_ids"] == ["D1:1"]
    assert raw["included_dialog_ids"] == ["D1:1"]
    assert raw["excluded_dialog_ids"] == ["D1:2"]
