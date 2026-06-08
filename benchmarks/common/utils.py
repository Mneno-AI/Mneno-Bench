"""File, identifier, timestamp, and token-estimation helpers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load newline-delimited JSON objects."""

    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            records.append(value)
    return records


def save_json(path: str | Path, value: Any) -> Path:
    """Serialize a value as readable JSON, creating parent directories."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return destination


def load_json(path: str | Path) -> Any:
    """Load a JSON value from disk."""

    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def generate_run_id(prefix: str = "run") -> str:
    """Generate a sortable run identifier."""

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{uuid4().hex[:8]}"


def now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 form."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def estimate_tokens(text: str) -> int:
    """Estimate tokens deterministically without requiring a model tokenizer."""

    pieces = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    return max(1, round(len(pieces) * 1.15)) if text else 0
