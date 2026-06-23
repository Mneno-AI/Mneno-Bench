"""Durable per-case checkpointing for LOCOMO runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from benchmarks.common.schema import BenchmarkResult, RunStatus
from benchmarks.common.utils import load_json, now_iso, save_json

CHECKPOINT_FORMAT = "mneno-bench.locomo.case"
CHECKPOINT_VERSION = 1
MANIFEST_FORMAT = "mneno-bench.locomo.checkpoint-manifest"
MANIFEST_VERSION = 1
CaseState = Literal["completed", "failed", "skipped"]


class CheckpointCompatibilityError(RuntimeError):
    """Raised when a resume request targets incompatible checkpoints."""


class LOCOMOCaseCheckpointStore:
    """Atomic case checkpoint store with manifest compatibility checks."""

    def __init__(
        self,
        directory: str | Path,
        fingerprint: str,
        evaluation_fingerprint: str | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.fingerprint = fingerprint
        self.evaluation_fingerprint = evaluation_fingerprint

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    def write_manifest(self, metadata: Mapping[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        save_json(
            self.manifest_path,
            {
                "format": MANIFEST_FORMAT,
                "version": MANIFEST_VERSION,
                "fingerprint": self.fingerprint,
                "evaluation_fingerprint": self.evaluation_fingerprint,
                "created_or_updated_at": now_iso(),
                "metadata": dict(metadata),
            },
        )

    def validate_for_resume(self) -> None:
        if not self.manifest_path.exists():
            return
        manifest = load_json(self.manifest_path)
        if not isinstance(manifest, dict):
            raise CheckpointCompatibilityError("Checkpoint manifest is not a JSON object.")
        if manifest.get("format") != MANIFEST_FORMAT:
            raise CheckpointCompatibilityError("Checkpoint manifest format is unsupported.")
        if manifest.get("version") != MANIFEST_VERSION:
            raise CheckpointCompatibilityError("Checkpoint manifest version is unsupported.")
        found = str(manifest.get("fingerprint", ""))
        if found != self.fingerprint:
            raise CheckpointCompatibilityError(
                "Checkpoint fingerprint mismatch; refusing unsafe resume. "
                f"expected={self.fingerprint} found={found}"
            )

    def path_for(self, dataset_index: int, case_id: str) -> Path:
        return self.directory / f"{dataset_index:06d}-{_safe_name(case_id)}.json"

    def save_case(self, dataset_index: int, result: BenchmarkResult) -> Path:
        state = case_state(result)
        envelope = {
            "format": CHECKPOINT_FORMAT,
            "version": CHECKPOINT_VERSION,
            "fingerprint": self.fingerprint,
            "evaluation_fingerprint": self.evaluation_fingerprint,
            "complete": True,
            "state": state,
            "case_id": result.case.id,
            "dataset_index": dataset_index,
            "completed_at": now_iso(),
            "system_statuses": _system_statuses(result),
            "result": result.model_dump(mode="json"),
        }
        return save_json(self.path_for(dataset_index, result.case.id), envelope)

    def load_cases(
        self,
        *,
        include_failed: bool = False,
        require_evaluation_fingerprint: bool = False,
    ) -> dict[str, BenchmarkResult]:
        cases: dict[str, BenchmarkResult] = {}
        if not self.directory.exists():
            return cases
        for path in sorted(self.directory.glob("*.json")):
            if path.name == self.manifest_path.name or path.name.startswith("."):
                continue
            loaded = self.load_case_file(
                path,
                require_evaluation_fingerprint=require_evaluation_fingerprint,
            )
            if loaded is not None and (include_failed or case_state(loaded) != "failed"):
                cases[loaded.case.id] = loaded
        return cases

    def load_case_file(
        self,
        path: str | Path,
        *,
        require_evaluation_fingerprint: bool = False,
    ) -> BenchmarkResult | None:
        try:
            envelope = load_json(path)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        if not isinstance(envelope, dict):
            return None
        if envelope.get("format") != CHECKPOINT_FORMAT:
            return None
        if envelope.get("version") != CHECKPOINT_VERSION:
            return None
        if envelope.get("fingerprint") != self.fingerprint:
            return None
        if require_evaluation_fingerprint and envelope.get("evaluation_fingerprint") != self.evaluation_fingerprint:
            return None
        if envelope.get("complete") is not True:
            return None
        result = envelope.get("result")
        if not isinstance(result, dict):
            return None
        try:
            return BenchmarkResult.model_validate(result)
        except Exception:
            return None


def locomo_checkpoint_fingerprint(parts: Mapping[str, Any]) -> str:
    """Stable compatibility fingerprint for safe LOCOMO resume."""

    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def case_state(result: BenchmarkResult) -> CaseState:
    statuses: list[RunStatus] = [baseline.status for baseline in result.baseline_results]
    if result.mneno_result is not None:
        statuses.append(result.mneno_result.status)
    if statuses and all(status == RunStatus.SKIPPED for status in statuses):
        return "skipped"
    if any(status == RunStatus.FAILED for status in statuses):
        return "failed"
    return "completed"


def _system_statuses(result: BenchmarkResult) -> dict[str, str]:
    statuses = {baseline.name: baseline.status.value for baseline in result.baseline_results}
    if result.mneno_result is not None:
        statuses["mneno"] = result.mneno_result.status.value
    return statuses


def _safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)
    return safe.strip("-") or "case"
