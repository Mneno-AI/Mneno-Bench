from pathlib import Path

import pytest

from benchmarks.mneno_suite.dataset import load_mneno_suite_dataset


def _write_dataset(tmp_path: Path, memory_lines: str, case_lines: str) -> Path:
    data_dir = tmp_path / "suite"
    data_dir.mkdir()
    (data_dir / "memories.jsonl").write_text(memory_lines, encoding="utf-8")
    (data_dir / "cases.jsonl").write_text(case_lines, encoding="utf-8")
    return data_dir


def _memory(memory_id: str = "m1") -> str:
    return (
        '{"id":"%s","content":"current fact","memory_type":"fact",'
        '"importance":1,"tags":[],"metadata":{}}\n' % memory_id
    )


def _case(category: str = "contradiction", expected: str = "m1") -> str:
    return (
        '{"id":"c1","category":"%s","query":"q",'
        '"expected_memory_ids":["%s"],"forbidden_memory_ids":["m1"],'
        '"expected_behavior":"use current","notes":""}\n' % (category, expected)
    )


def test_valid_context_rot_dataset_loads() -> None:
    dataset = load_mneno_suite_dataset(Path("data/mneno_suite"))

    assert len(dataset.memories) == 48
    assert len(dataset.cases) == 24
    assert len({case.category for case in dataset.cases}) == 8


def test_duplicate_memory_ids_fail(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path, _memory() + _memory(), _case())
    with pytest.raises(ValueError, match="Duplicate memory IDs: m1"):
        load_mneno_suite_dataset(path)


def test_missing_expected_ids_fail(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path, _memory(), _case(expected="missing"))
    with pytest.raises(ValueError, match="missing expected memory IDs: missing"):
        load_mneno_suite_dataset(path)


def test_unknown_category_fails(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path, _memory(), _case(category="unknown"))
    with pytest.raises(ValueError, match="Invalid record"):
        load_mneno_suite_dataset(path)


def test_invalid_jsonl_fails(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path, "{bad json}\n", _case())
    with pytest.raises(ValueError, match="Invalid JSONL"):
        load_mneno_suite_dataset(path)
