from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmarks.locomo.config import LOCOMOEvaluationConfig
from benchmarks.locomo.run import _cli_config_overrides, _load_config


def test_locomo_evaluation_config_defaults() -> None:
    config = LOCOMOEvaluationConfig()

    assert config.mode == "retrieval_only"
    assert config.judge_model is None
    assert config.workers == 1
    assert config.strict_dataset_validation
    assert not config.allow_malformed_evidence


def test_locomo_evaluation_config_validates_mode() -> None:
    with pytest.raises(ValidationError):
        LOCOMOEvaluationConfig.model_validate({"mode": "official_magic"})


def test_locomo_evaluation_config_rejects_non_positive_workers() -> None:
    with pytest.raises(ValidationError):
        LOCOMOEvaluationConfig(workers=0)


def test_allow_malformed_requires_non_strict_validation() -> None:
    with pytest.raises(ValidationError, match="strict_dataset_validation"):
        LOCOMOEvaluationConfig(allow_malformed_evidence=True)


def test_mneno_reranker_requires_explicit_external_calls() -> None:
    with pytest.raises(ValidationError, match="allow_external_calls"):
        LOCOMOEvaluationConfig(
            mneno_reranker_model="nvidia_nim/ranking/nvidia/reranker"
        )


def test_mneno_reranker_configuration_is_bounded() -> None:
    config = LOCOMOEvaluationConfig(
        allow_external_calls=True,
        mneno_reranker_model="nvidia_nim/ranking/nvidia/reranker",
        mneno_reranker_candidate_limit=50,
    )

    assert config.mneno_reranker_candidate_limit == 50
    with pytest.raises(ValidationError):
        LOCOMOEvaluationConfig(
            allow_external_calls=True,
            mneno_reranker_model="nvidia_nim/ranking/nvidia/reranker",
            mneno_reranker_candidate_limit=513,
        )


def test_cli_overrides_config_only_for_explicit_execution_options(tmp_path: Path) -> None:
    config_path = tmp_path / "locomo.yaml"
    config_path.write_text(
        "\n".join(
            [
                "mode: retrieval_only",
                "max_cases: 5",
                "resume: false",
                "phase: full",
                "external_requests_per_minute: 99",
                "external_max_concurrent_requests: 3",
                "external_retries: 4",
            ]
        ),
        encoding="utf-8",
    )

    overrides = _cli_config_overrides(
        resume=True,
        phase="evaluate_only",
        checkpoint_dir=tmp_path / "checkpoints",
        results_dir=tmp_path / "results",
        max_cases=None,
        external_requests_per_minute=10,
        external_max_concurrent_requests=None,
        external_retries=None,
    )
    config = LOCOMOEvaluationConfig.from_yaml(config_path, overrides)

    assert config.resume is True
    assert config.phase == "evaluate_only"
    assert config.max_cases == 5
    assert config.external_requests_per_minute == 10
    assert config.external_max_concurrent_requests == 3
    assert config.external_retries == 4
    assert config.checkpoint_dir == str(tmp_path / "checkpoints")
    assert config.output_dir == str(tmp_path / "results")


def test_llm_judge_uses_model_environment_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITELLM_MODEL", "nvidia_nim/meta/llama-3.1-70b-instruct")
    monkeypatch.setenv("LITELLM_PROVIDER", "nvidia_nim")

    config = _load_config(
        None,
        5,
        LOCOMOEvaluationConfig(mode="llm_judge", allow_external_calls=True),
    )

    assert config.judge_model == "nvidia_nim/meta/llama-3.1-70b-instruct"
    assert config.judge_provider == "nvidia_nim"
