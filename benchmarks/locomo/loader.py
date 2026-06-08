"""Load official or normalized LOCOMO JSON from an optional local dataset copy."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from benchmarks.locomo.schema import (
    LOCOMOConversation,
    LOCOMODataset,
    LOCOMOMessage,
    LOCOMOQuestion,
)
from benchmarks.locomo.validator import (
    LOCOMODatasetMissingError,
    LOCOMOValidationError,
    validate_locomo_dataset,
)

DEFAULT_FILENAMES = (
    "raw/locomo10.json",
    "processed/locomo10.json",
    "locomo10.json",
    "raw/locomo.json",
    "processed/locomo.json",
    "locomo.json",
)
SESSION_PATTERN = re.compile(r"^session_(\d+)$")


def load_locomo_dataset(
    path: str | Path, allow_malformed_evidence: bool = False
) -> LOCOMODataset:
    """Load and validate a LOCOMO dataset directory or explicit JSON file."""

    source = resolve_locomo_path(path)
    try:
        with source.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise LOCOMOValidationError(
            f"Malformed LOCOMO JSON in {source}: {exc.msg} at line {exc.lineno}."
        ) from exc

    try:
        dataset = _parse_payload(payload, source)
    except ValidationError as exc:
        raise LOCOMOValidationError(
            f"Malformed LOCOMO record in {source}: {exc}"
        ) from exc
    return validate_locomo_dataset(
        dataset, allow_malformed_evidence=allow_malformed_evidence
    )


def resolve_locomo_path(path: str | Path) -> Path:
    source = Path(path)
    if source.is_file():
        return source
    candidates = [source / name for name in DEFAULT_FILENAMES]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    expected = ", ".join(str(candidate) for candidate in candidates)
    raise LOCOMODatasetMissingError(
        f"LOCOMO dataset missing. Expected one of: {expected}"
    )


def _parse_payload(payload: Any, source: Path) -> LOCOMODataset:
    if isinstance(payload, dict) and isinstance(payload.get("conversations"), list):
        return LOCOMODataset.model_validate({**payload, "source_path": str(source)})
    if not isinstance(payload, list):
        raise LOCOMOValidationError(
            "LOCOMO root must be the official sample list or an object with "
            "a 'conversations' list."
        )
    conversations = [
        _parse_official_conversation(value, index)
        for index, value in enumerate(payload, start=1)
    ]
    return LOCOMODataset(
        conversations=conversations,
        source_path=str(source),
        metadata={"source_format": "official_locomo10"},
    )


def _parse_official_conversation(value: Any, index: int) -> LOCOMOConversation:
    if not isinstance(value, dict):
        raise LOCOMOValidationError(
            f"Malformed LOCOMO conversation at index {index}: expected an object."
        )
    conversation_id = str(value.get("sample_id") or value.get("id") or "").strip()
    raw_conversation = value.get("conversation")
    raw_questions = value.get("qa", value.get("questions"))
    if not conversation_id:
        raise LOCOMOValidationError(
            f"Malformed LOCOMO conversation at index {index}: missing sample_id."
        )
    if not isinstance(raw_conversation, dict):
        raise LOCOMOValidationError(
            f"Conversation {conversation_id!r} has no conversation object."
        )
    if not isinstance(raw_questions, list):
        raise LOCOMOValidationError(f"Conversation {conversation_id!r} has no qa list.")

    messages: list[LOCOMOMessage] = []
    sequence_index = 0
    session_entries = sorted(
        (
            (int(match.group(1)), key, turns)
            for key, turns in raw_conversation.items()
            if (match := SESSION_PATTERN.match(key)) is not None
        ),
        key=lambda item: item[0],
    )
    for session_index, session_id, turns in session_entries:
        if turns is None:
            continue
        if not isinstance(turns, list):
            raise LOCOMOValidationError(
                f"Conversation {conversation_id!r} session {session_id!r} "
                "must be a list."
            )
        timestamp = raw_conversation.get(f"{session_id}_date_time")
        for turn_index, turn in enumerate(turns, start=1):
            if not isinstance(turn, dict):
                raise LOCOMOValidationError(
                    f"Conversation {conversation_id!r} session {session_id!r} "
                    f"turn {turn_index} must be an object."
                )
            messages.append(
                LOCOMOMessage(
                    id=str(turn.get("dia_id") or turn.get("id") or ""),
                    speaker=str(turn.get("speaker") or ""),
                    text=str(turn.get("text") or ""),
                    session_id=session_id,
                    session_index=session_index,
                    sequence_index=sequence_index,
                    timestamp=str(timestamp) if timestamp is not None else None,
                    metadata={
                        key: item
                        for key, item in turn.items()
                        if key not in {"dia_id", "id", "speaker", "text"}
                    },
                )
            )
            sequence_index += 1

    questions = [
        _parse_official_question(item, conversation_id, question_index)
        for question_index, item in enumerate(raw_questions, start=1)
    ]
    return LOCOMOConversation(
        id=conversation_id,
        messages=messages,
        questions=questions,
        speaker_a=_optional_string(raw_conversation.get("speaker_a")),
        speaker_b=_optional_string(raw_conversation.get("speaker_b")),
        metadata={
            "observation": value.get("observation"),
            "session_summary": value.get("session_summary"),
            "event_summary": value.get("event_summary"),
        },
    )


def _parse_official_question(
    value: Any, conversation_id: str, index: int
) -> LOCOMOQuestion:
    if not isinstance(value, dict):
        raise LOCOMOValidationError(
            f"Conversation {conversation_id!r} question {index} must be an object."
        )
    if "category" not in value:
        raise LOCOMOValidationError(
            f"Conversation {conversation_id!r} question {index} is missing category."
        )
    raw_answer = value.get("answer", value.get("expected_answer"))
    if isinstance(raw_answer, list):
        answers = [str(answer) for answer in raw_answer]
    elif raw_answer is None:
        answers = []
    else:
        answers = [str(raw_answer)]
    evidence = value.get("evidence", value.get("evidence_ids", []))
    evidence_ids = _normalize_evidence_ids(evidence)
    question_id = str(value.get("id") or f"{conversation_id}:qa-{index:04d}")
    return LOCOMOQuestion(
        id=question_id,
        conversation_id=conversation_id,
        question=str(value.get("question") or ""),
        expected_answers=answers,
        category=value["category"],
        evidence_ids=evidence_ids,
        metadata={
            "answer_available": bool(answers),
            **{
                key: item
                for key, item in value.items()
                if key
                not in {
                    "id",
                    "question",
                    "answer",
                    "expected_answer",
                    "category",
                    "evidence",
                    "evidence_ids",
                }
            },
        },
    )


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _normalize_evidence_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if not item:
            continue
        for part in re.split(r"[;,]", str(item)):
            cleaned = part.strip().replace("(", "").replace(")", "")
            if cleaned:
                ids.append(cleaned)
    return ids
