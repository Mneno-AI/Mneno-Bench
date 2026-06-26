"""Explicit structural and reference validation for LOCOMO datasets."""

from __future__ import annotations

from collections.abc import Iterable

from benchmarks.locomo.schema import LOCOMODataset


class LOCOMOValidationError(ValueError):
    """Raised when a local LOCOMO copy violates the supported schema."""


class LOCOMODatasetMissingError(FileNotFoundError):
    """Raised when no supported LOCOMO dataset file is present."""


def validate_locomo_dataset(
    dataset: LOCOMODataset, allow_malformed_evidence: bool = False
) -> LOCOMODataset:
    """Validate stable IDs and all question-to-dialog evidence references."""

    if not dataset.conversations:
        raise LOCOMOValidationError("LOCOMO dataset contains no conversations.")

    _ensure_unique(
        (conversation.id for conversation in dataset.conversations), "conversation"
    )
    all_question_ids: list[str] = []

    for conversation in dataset.conversations:
        if not conversation.messages:
            raise LOCOMOValidationError(
                f"Conversation {conversation.id!r} contains no messages."
            )
        if not conversation.questions:
            raise LOCOMOValidationError(
                f"Conversation {conversation.id!r} contains no questions."
            )
        message_ids = [message.id for message in conversation.messages]
        question_ids = [question.id for question in conversation.questions]
        _ensure_unique(message_ids, f"message in conversation {conversation.id!r}")
        _ensure_unique(question_ids, f"question in conversation {conversation.id!r}")
        message_id_set = set(message_ids)
        for question in conversation.questions:
            if question.conversation_id != conversation.id:
                raise LOCOMOValidationError(
                    f"Question {question.id!r} references conversation "
                    f"{question.conversation_id!r}, expected {conversation.id!r}."
                )
            missing = sorted(set(question.evidence_ids) - message_id_set)
            if missing:
                if allow_malformed_evidence:
                    continue
                raise LOCOMOValidationError(
                    f"Question {question.id!r} references missing dialog IDs: "
                    f"{', '.join(missing)}"
                )
        all_question_ids.extend(question_ids)

    _ensure_unique(all_question_ids, "question")
    return dataset


def locomo_validation_warnings(dataset: LOCOMODataset) -> list[dict[str, object]]:
    """Return non-fatal evidence warnings without mutating the dataset."""

    warnings: list[dict[str, object]] = []
    for conversation in dataset.conversations:
        message_ids = {message.id for message in conversation.messages}
        for question in conversation.questions:
            missing = sorted(set(question.evidence_ids) - message_ids)
            if missing:
                warnings.append(
                    {
                        "type": "missing_evidence_reference",
                        "conversation_id": conversation.id,
                        "question_id": question.id,
                        "missing_evidence_ids": missing,
                    }
                )
    return warnings


def _ensure_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise LOCOMOValidationError(
            f"Duplicate {label} IDs: {', '.join(sorted(duplicates))}"
        )
