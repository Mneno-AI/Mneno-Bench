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
    DATASET_MISSING = "dataset_missing"


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
    value: float | None
    unit: str = "ratio"
    description: str = ""
    unavailable_reason: str | None = None
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


class MnenoCapabilityReport(BaseModel):
    """Runtime feature discovery for the installed optional Mneno SDK."""

    available: bool
    version: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    partial: bool = False


class MnenoMemoryLoadRecord(BaseModel):
    """Dataset-to-Core identity and conflict facts from one memory insertion."""

    dataset_memory_id: str
    mneno_memory_id: str
    conflict_reports: list[dict[str, Any]] = Field(default_factory=list)
    resolution_actions: list[dict[str, Any] | str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)


class MnenoExecutionSummary(BaseModel):
    """Suite-level facts about realistic Mneno Core setup and execution."""

    memories_loaded: int = 0
    sessions_created: int = 0
    conflicts_detected: int = 0
    hierarchy_evaluated: bool = False
    hierarchy_transitions: dict[str, int] = Field(default_factory=dict)
    compaction_previewed: bool = False
    compaction_stats: dict[str, int | float] = Field(default_factory=dict)
    traces_exported: int = 0
    session_id_map: dict[str, str] = Field(default_factory=dict)
    memory_id_map: dict[str, str] = Field(default_factory=dict)
    memory_loads: list[MnenoMemoryLoadRecord] = Field(default_factory=list)
    capability_errors: dict[str, str] = Field(default_factory=dict)
    capability_report: MnenoCapabilityReport


class MnenoDecisionSummary(BaseModel):
    """Normalized trace and context decisions for one suite case."""

    retrieved_ids: list[str] = Field(default_factory=list)
    included_ids: list[str] = Field(default_factory=list)
    excluded_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    inclusion_reasons: dict[str, list[str]] = Field(default_factory=dict)
    exclusion_reasons: dict[str, list[str]] = Field(default_factory=dict)
    conflict_events: list[dict[str, Any]] = Field(default_factory=list)
    hierarchy_events: list[dict[str, Any]] = Field(default_factory=list)
    session_events: list[dict[str, Any]] = Field(default_factory=list)


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
    included_memory_ids: list[str] = Field(default_factory=list)
    excluded_memory_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    decision_summary: MnenoDecisionSummary | None = None
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
