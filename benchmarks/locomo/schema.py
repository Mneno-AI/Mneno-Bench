"""Typed, provider-independent schema for the released LOCOMO dataset."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LOCOMOMessage(BaseModel):
    """One dialog turn from a LOCOMO conversation session."""

    model_config = ConfigDict(extra="allow")

    id: str
    speaker: str
    text: str
    session_id: str
    session_index: int = Field(ge=1)
    sequence_index: int = Field(ge=0)
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "speaker", "text", "session_id")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    def as_benchmark_memory(self, conversation_id: str) -> dict[str, Any]:
        content = f"{self.speaker}: {self.text}"
        if self.timestamp:
            content = f"({self.timestamp}) {content}"
        return {
            "id": self.id,
            "content": content,
            "text": content,
            "memory_type": "episodic",
            "session_id": f"{conversation_id}:{self.session_id}",
            "sequence_index": self.sequence_index,
            "importance": 0.5,
            "tags": ["locomo", conversation_id, self.session_id],
            "metadata": {
                **self.metadata,
                "benchmark": "locomo",
                "conversation_id": conversation_id,
                "dialog_id": self.id,
                "session_id": self.session_id,
                "session_index": self.session_index,
                "timestamp": self.timestamp,
            },
        }


class LOCOMOQuestion(BaseModel):
    """One annotated LOCOMO question and its official evidence references."""

    model_config = ConfigDict(extra="allow")

    id: str
    conversation_id: str
    question: str
    expected_answers: list[str]
    category: int | str
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "conversation_id", "question")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class LOCOMOConversation(BaseModel):
    """A complete multi-session LOCOMO conversation and its questions."""

    model_config = ConfigDict(extra="allow")

    id: str
    messages: list[LOCOMOMessage]
    questions: list[LOCOMOQuestion]
    speaker_a: str | None = None
    speaker_b: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def require_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @property
    def message_by_id(self) -> dict[str, LOCOMOMessage]:
        return {message.id: message for message in self.messages}


class LOCOMODataset(BaseModel):
    """Validated local representation of an official LOCOMO release."""

    model_config = ConfigDict(extra="allow")

    conversations: list[LOCOMOConversation]
    source_path: str
    benchmark_version: str = "locomo10"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def conversation_by_id(self) -> dict[str, LOCOMOConversation]:
        return {conversation.id: conversation for conversation in self.conversations}

    @property
    def message_count(self) -> int:
        return sum(len(conversation.messages) for conversation in self.conversations)

    @property
    def question_count(self) -> int:
        return sum(len(conversation.questions) for conversation in self.conversations)
