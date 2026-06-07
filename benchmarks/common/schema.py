"""Pydantic models for durable, local benchmark result exports."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    """Lifecycle states shared by runs and system results."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BenchmarkCase(BaseModel):
    """A query and its expected memory evidence."""

    model_config = ConfigDict(extra="allow")

    id: str
    query: str
    expected_memory_ids: list[str] = Field(default_factory=list)
    stale_memory_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricResult(BaseModel):
    """A deterministic metric value and its interpretation."""

    name: str
    value: float
    unit: str = "ratio"
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedSearchResult(BaseModel):
    """Provider-independent representation of a search evaluation."""

    provider: str
    query: str
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    trace_id: str | None = None
    raw_result: Any = None


class NormalizedContextResult(BaseModel):
    """Provider-independent representation of a context evaluation."""

    provider: str
    query: str
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    trace_id: str | None = None
    raw_result: Any = None


class NormalizedCompactionResult(BaseModel):
    """Provider-independent representation of a compaction evaluation."""

    provider: str
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    trace_id: str | None = None
    raw_result: Any = None


class TraceSummary(BaseModel):
    """Compact trace fields designed to align with future Mneno Core exports."""

    trace_id: str | None = None
    operation_count: int = 0
    event_count: int = 0
    decision_count: int = 0
    duration_ms: float | None = None
    retrieved_memory_ids: list[str] = Field(default_factory=list)
    selected_memory_ids: list[str] = Field(default_factory=list)
    suppressed_memory_ids: list[str] = Field(default_factory=list)
    conflict_resolutions: list[str] = Field(default_factory=list)
    lifecycle_events: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    explainability_coverage: float | None = None
    raw_trace_reference: str | None = None


class BaselineResult(BaseModel):
    """Result emitted by a baseline retrieval strategy."""

    name: str
    status: RunStatus = RunStatus.COMPLETED
    retrieved_memory_ids: list[str] = Field(default_factory=list)
    context_tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MnenoResult(BaseModel):
    """Result emitted by the Mneno system under test."""

    status: RunStatus
    retrieved_memory_ids: list[str] = Field(default_factory=list)
    context_tokens: int = 0
    latency_ms: float = 0.0
    trace_summary: TraceSummary | None = None
    skip_reason: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkResult(BaseModel):
    """All system outputs and metrics for one benchmark case."""

    case: BenchmarkCase
    baseline_results: list[BaselineResult] = Field(default_factory=list)
    mneno_result: MnenoResult | None = None
    metrics: dict[str, list[MetricResult]] = Field(default_factory=dict)


class BenchmarkRun(BaseModel):
    """Top-level JSON document written for each benchmark execution."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    benchmark_version: str = "0.2.0"
    mneno_version: str | None = None
    run_id: str
    suite: str
    status: RunStatus
    started_at: str
    finished_at: str | None = None
    systems: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    results: list[BenchmarkResult] = Field(default_factory=list)
    summary_metrics: dict[str, list[MetricResult]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    export_metadata: dict[str, Any] = Field(default_factory=dict)
