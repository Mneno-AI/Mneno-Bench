import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.locomo.dataset import LOCOMOValidationError, load_locomo_dataset


def _sample() -> dict[str, Any]:
    return {
        "sample_id": "conv-test",
        "conversation": {
            "speaker_a": "Alex",
            "speaker_b": "Blair",
            "session_1_date_time": "10:00 am on 1 January, 2024",
            "session_1": [
                {"speaker": "Alex", "dia_id": "D1:1", "text": "I moved to Rome."},
                {"speaker": "Blair", "dia_id": "D1:2", "text": "How is Rome?"},
            ],
            "session_2_date_time": "11:00 am on 2 January, 2024",
            "session_2": [
                {"speaker": "Alex", "dia_id": "D2:1", "text": "It is sunny."}
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
        "observation": {},
        "session_summary": {},
        "event_summary": {},
    }


def _write(tmp_path: Path, payload: Any) -> Path:
    path = tmp_path / "locomo10.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_official_dataset_loads(tmp_path: Path) -> None:
    dataset = load_locomo_dataset(_write(tmp_path, [_sample()]))

    assert len(dataset.conversations) == 1
    assert dataset.message_count == 3
    assert dataset.question_count == 1
    assert dataset.conversations[0].questions[0].expected_answers == ["Rome"]
    assert dataset.conversations[0].questions[0].evidence_ids == ["D1:1"]


def test_malformed_dataset_fails(tmp_path: Path) -> None:
    sample = _sample()
    del sample["qa"][0]["question"]

    with pytest.raises(LOCOMOValidationError, match="question"):
        load_locomo_dataset(_write(tmp_path, [sample]))


def test_duplicate_ids_fail(tmp_path: Path) -> None:
    sample = _sample()
    sample["conversation"]["session_1"][1]["dia_id"] = "D1:1"

    with pytest.raises(LOCOMOValidationError, match="Duplicate message"):
        load_locomo_dataset(_write(tmp_path, [sample]))


def test_missing_references_fail(tmp_path: Path) -> None:
    sample = _sample()
    sample["qa"][0]["evidence"] = ["D9:9"]

    with pytest.raises(LOCOMOValidationError, match="missing dialog IDs: D9:9"):
        load_locomo_dataset(_write(tmp_path, [sample]))
