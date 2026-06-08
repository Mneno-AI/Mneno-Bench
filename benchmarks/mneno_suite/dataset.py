"""Typed loader for the deterministic Mneno Context Rot Suite v1 dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MnenoSuiteCategory = Literal[
    "stale_preference",
    "preference_change",
    "contradiction",
    "lifecycle_priority",
    "session_continuity",
    "context_budget",
    "compaction_retention",
    "explainability",
]


class MnenoSuiteMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    content: str
    memory_type: str
    layer: str | None = None
    status: str | None = None
    importance: float = Field(ge=0.0, le=1.0)
    session_id: str | None = None
    sequence_index: int | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)
    expected_status: str | None = None
    expected_layer: str | None = None
    conflict_group: str | None = None
    supersedes: str | None = None
    stale: bool | None = None
    noise: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def as_benchmark_memory(self) -> dict[str, Any]:
        value = self.model_dump(mode="json")
        value["text"] = self.content
        metadata = dict(value["metadata"])
        metadata.setdefault("created_order", self.sequence_index)
        metadata.setdefault("expected_status", self.expected_status or self.status)
        metadata.setdefault("expected_layer", self.expected_layer or self.layer)
        metadata.setdefault("conflict_group", self.conflict_group)
        metadata.setdefault("supersedes", self.supersedes or metadata.get("supersedes"))
        metadata.setdefault(
            "stale",
            self.stale
            if self.stale is not None
            else (self.status in {"stale", "superseded", "rejected"}),
        )
        metadata.setdefault(
            "noise",
            self.noise if self.noise is not None else ("noise" in self.tags),
        )
        value["metadata"] = metadata
        return value


class MnenoSuiteCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: MnenoSuiteCategory
    query: str
    expected_memory_ids: list[str] = Field(default_factory=list)
    forbidden_memory_ids: list[str] = Field(default_factory=list)
    expected_behavior: str
    budget: int | None = Field(default=None, ge=1)
    current_session_id: str | None = None
    notes: str = ""


class MnenoSuiteDataset(BaseModel):
    memories: list[MnenoSuiteMemory]
    cases: list[MnenoSuiteCase]

    @property
    def memory_by_id(self) -> dict[str, MnenoSuiteMemory]:
        return {memory.id: memory for memory in self.memories}


def load_mneno_suite_dataset(data_dir: Path) -> MnenoSuiteDataset:
    memories = _load_jsonl(data_dir / "memories.jsonl", MnenoSuiteMemory)
    cases = _load_jsonl(data_dir / "cases.jsonl", MnenoSuiteCase)
    _ensure_unique_ids(memories, "memory")
    _ensure_unique_ids(cases, "case")

    memory_ids = {memory.id for memory in memories}
    for case in cases:
        missing_expected = sorted(set(case.expected_memory_ids) - memory_ids)
        if missing_expected:
            raise ValueError(
                f"Case {case.id!r} references missing expected memory IDs: "
                f"{', '.join(missing_expected)}"
            )
        missing_forbidden = sorted(set(case.forbidden_memory_ids) - memory_ids)
        if missing_forbidden:
            raise ValueError(
                f"Case {case.id!r} references missing forbidden memory IDs: "
                f"{', '.join(missing_forbidden)}"
            )
    return MnenoSuiteDataset(memories=memories, cases=cases)


def _load_jsonl(path: Path, model: type[BaseModel]) -> list[Any]:
    records: list[Any] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSONL in {path} at line {line_number}: {exc.msg}"
                    ) from exc
                try:
                    records.append(model.model_validate(value))
                except ValidationError as exc:
                    raise ValueError(
                        f"Invalid record in {path} at line {line_number}: {exc}"
                    ) from exc
    except FileNotFoundError as exc:
        raise ValueError(f"Missing Mneno suite dataset file: {path}") from exc
    return records


def _ensure_unique_ids(records: list[Any], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        record_id = str(record.id)
        if record_id in seen:
            duplicates.add(record_id)
        seen.add(record_id)
    if duplicates:
        raise ValueError(f"Duplicate {label} IDs: {', '.join(sorted(duplicates))}")
