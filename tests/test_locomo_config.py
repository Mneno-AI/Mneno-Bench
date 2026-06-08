import pytest
from pydantic import ValidationError

from benchmarks.locomo.config import LOCOMOEvaluationConfig


def test_locomo_evaluation_config_defaults() -> None:
    config = LOCOMOEvaluationConfig()

    assert config.mode == "retrieval_only"
    assert config.judge_model is None
    assert config.strict_dataset_validation
    assert not config.allow_malformed_evidence


def test_locomo_evaluation_config_validates_mode() -> None:
    with pytest.raises(ValidationError):
        LOCOMOEvaluationConfig.model_validate({"mode": "official_magic"})


def test_allow_malformed_requires_non_strict_validation() -> None:
    with pytest.raises(ValidationError, match="strict_dataset_validation"):
        LOCOMOEvaluationConfig(allow_malformed_evidence=True)
