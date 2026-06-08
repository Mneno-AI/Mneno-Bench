import json
from pathlib import Path
from typing import Any

from benchmarks.common.schema import (
    NormalizedContextResult,
    NormalizedSearchResult,
    RunStatus,
)
from benchmarks.locomo.config import LOCOMOEvaluationConfig
from benchmarks.locomo.run import run_locomo


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


class MissingMnenoAdapter:
    def is_available(self) -> bool:
        return False


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
    assert len(list((tmp_path / "results" / "locomo" / "traces").glob("*.json"))) == 3
    assert len(list((tmp_path / "results" / "locomo" / "raw").rglob("*.json"))) == 1
