import json
from pathlib import Path

import pytest

from benchmarks.common.llm_client import LLMConfig
from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    MnenoResult,
    NormalizedSearchResult,
    RunStatus,
)
from benchmarks.common.utils import load_json
from benchmarks.locomo.checkpoints import (
    CheckpointCompatibilityError,
    LOCOMOCaseCheckpointStore,
    case_state,
)
from benchmarks.locomo.config import LOCOMOEvaluationConfig
from benchmarks.locomo.judge import LOCOMOJudge
from benchmarks.locomo.run import run_locomo
from tests.test_locomo_runner import FakeMnenoAdapter, _write_dataset, _write_two_conversation_dataset


def _result(case_id: str, status: RunStatus = RunStatus.COMPLETED) -> BenchmarkResult:
    return BenchmarkResult(
        case=BenchmarkCase(id=case_id, query="q"),
        baseline_results=[BaselineResult(name="keyword_baseline")],
        mneno_result=MnenoResult(status=status, error="boom" if status == RunStatus.FAILED else None),
        metrics={},
    )


def test_atomic_checkpoint_loader_ignores_partial_and_corrupt_files(tmp_path: Path) -> None:
    store = LOCOMOCaseCheckpointStore(tmp_path, "fingerprint")
    store.write_manifest({"test": True})
    store.save_case(0, _result("done"))
    (tmp_path / "000001-partial.json").write_text(
        json.dumps({"format": "mneno-bench.locomo.case", "complete": False}),
        encoding="utf-8",
    )
    (tmp_path / "000002-corrupt.json").write_text("{", encoding="utf-8")
    (tmp_path / ".000003-temp.json.tmp").write_text("{}", encoding="utf-8")

    loaded = store.load_cases()

    assert list(loaded) == ["done"]
    assert loaded["done"].case.id == "done"
    assert (tmp_path / ".000003-temp.json.tmp").exists()


def test_checkpoint_records_failed_and_skipped_case_states(tmp_path: Path) -> None:
    store = LOCOMOCaseCheckpointStore(tmp_path, "fingerprint")
    failed = _result("failed", RunStatus.FAILED)
    skipped = BenchmarkResult(
        case=BenchmarkCase(id="skipped", query="q"),
        baseline_results=[BaselineResult(name="keyword_baseline", status=RunStatus.SKIPPED)],
        mneno_result=MnenoResult(status=RunStatus.SKIPPED, skip_reason="missing"),
    )

    failed_path = store.save_case(0, failed)
    skipped_path = store.save_case(1, skipped)

    assert case_state(failed) == "failed"
    assert load_json(failed_path)["state"] == "failed"
    assert case_state(skipped) == "skipped"
    assert load_json(skipped_path)["state"] == "skipped"


def test_resume_reuses_completed_cases_and_preserves_dataset_order(tmp_path: Path) -> None:
    _write_two_conversation_dataset(tmp_path / "data")
    config = LOCOMOEvaluationConfig(workers=1)
    first = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
        evaluation_config=config,
    )
    checkpoint_dir = Path(first.export_metadata["checkpointing"]["checkpoint_dir"])
    case_files = sorted(path for path in checkpoint_dir.glob("*.json") if path.name != "manifest.json")
    assert len(case_files) == 2
    case_files[1].unlink()

    resumed = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
        evaluation_config=config.model_copy(update={"resume": True}),
    )

    assert resumed.export_metadata["checkpointing"]["resumed_cases"] == 1
    assert [result.case.id for result in resumed.results] == [
        result.case.id for result in first.results
    ]


class Flaky429MnenoAdapter(FakeMnenoAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def evaluate_search(self, **kwargs: object) -> NormalizedSearchResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("HTTP 429 too many requests")
        return super().evaluate_search(**kwargs)


class FakeJudgeClient:
    config = LLMConfig(model="fake-judge", provider="test", api_key_required=False)

    def generate(self, prompt: str, **overrides: object) -> str:
        del prompt, overrides
        return '{"correct": true, "score": 1.0, "reason": "ok"}'


def test_failed_checkpoint_is_retried_and_can_succeed_on_resume(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")
    adapter = Flaky429MnenoAdapter()
    config = LOCOMOEvaluationConfig(workers=1)

    first = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=adapter,  # type: ignore[arg-type]
        evaluation_config=config,
    )
    assert first.results[0].mneno_result is not None
    assert first.results[0].mneno_result.status == RunStatus.FAILED

    resumed = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=adapter,  # type: ignore[arg-type]
        evaluation_config=config.model_copy(update={"resume": True}),
    )

    assert resumed.export_metadata["checkpointing"]["resumed_cases"] == 0
    assert adapter.calls == 2
    assert resumed.results[0].mneno_result is not None
    assert resumed.results[0].mneno_result.status == RunStatus.COMPLETED


def test_predict_only_checkpoints_are_judged_by_evaluate_only(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data")
    predict_config = LOCOMOEvaluationConfig(
        mode="llm_judge",
        phase="predict_only",
        judge_model="fake-judge",
        workers=1,
    )
    prediction = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
        evaluation_config=predict_config,
    )
    predicted_judge = prediction.results[0].baseline_results[0].metadata["judge_result"]
    assert predicted_judge is None

    judged = run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
        evaluation_config=predict_config.model_copy(
            update={"phase": "evaluate_only", "resume": True}
        ),
        judge=LOCOMOJudge(FakeJudgeClient()),
    )

    result = judged.results[0]
    judge_result = result.baseline_results[0].metadata["judge_result"]
    assert judged.export_metadata["checkpointing"]["resumed_cases"] == 1
    assert judge_result["status"] == "completed"
    assert {metric.name: metric.value for metric in result.metrics["keyword_baseline"]}[
        "judge_score"
    ] == 1.0
    checkpoint_dir = Path(judged.export_metadata["checkpointing"]["checkpoint_dir"])
    checkpoint_payloads = [
        load_json(path)
        for path in checkpoint_dir.glob("*.json")
        if path.name != "manifest.json"
    ]
    assert checkpoint_payloads[0]["result"]["baseline_results"][0]["metadata"][
        "judge_result"
    ]["status"] == "completed"


def test_resume_refuses_explicit_checkpoint_fingerprint_mismatch(tmp_path: Path) -> None:
    _write_two_conversation_dataset(tmp_path / "data")
    checkpoint_dir = tmp_path / "checkpoints"
    config = LOCOMOEvaluationConfig(workers=1, checkpoint_dir=str(checkpoint_dir))
    run_locomo(
        tmp_path / "data",
        tmp_path / "results",
        adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
        evaluation_config=config,
        k=5,
    )

    with pytest.raises(CheckpointCompatibilityError, match="fingerprint mismatch"):
        run_locomo(
            tmp_path / "data",
            tmp_path / "results",
            adapter=FakeMnenoAdapter(),  # type: ignore[arg-type]
            evaluation_config=config.model_copy(update={"resume": True}),
            k=6,
        )
