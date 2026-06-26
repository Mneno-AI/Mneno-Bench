"""Durable models and aggregation for deterministic failure analysis."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


BASELINE_PROVIDERS = {
    "keyword_baseline",
    "full_context_baseline",
    "random_baseline",
}


class FailureCategory(str, Enum):
    RETRIEVAL_FAILURE = "retrieval_failure"
    RANKING_FAILURE = "ranking_failure"
    CONTEXT_BUDGET_FAILURE = "context_budget_failure"
    LIFECYCLE_FILTER_FAILURE = "lifecycle_filter_failure"
    SESSION_CONTINUITY_FAILURE = "session_continuity_failure"
    CONFLICT_RESOLUTION_FAILURE = "conflict_resolution_failure"
    COMPACTION_FAILURE = "compaction_failure"
    ANSWER_GENERATION_FAILURE = "answer_generation_failure"
    JUDGE_FAILURE = "judge_failure"
    DATASET_ISSUE = "dataset_issue"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class FailureSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureCase(BaseModel):
    """One evidence-backed failure classification for one provider and case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    benchmark: str
    case_id: str
    provider: str
    category: FailureCategory
    severity: FailureSeverity
    query: str
    expected_ids: list[str] = Field(default_factory=list)
    retrieved_ids: list[str] = Field(default_factory=list)
    included_ids: list[str] = Field(default_factory=list)
    excluded_ids: list[str] = Field(default_factory=list)
    forbidden_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    suggested_action: str
    expected_behavior: bool = False
    interpretation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RootCauseSummary(BaseModel):
    """Deterministic aggregate counts for a failure report."""

    total_failures: int = Field(default=0, ge=0)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_provider: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    top_suggested_actions: list[str] = Field(default_factory=list)

    @classmethod
    def from_failures(cls, failures: list[FailureCase]) -> RootCauseSummary:
        actions = Counter(failure.suggested_action for failure in failures)
        return cls(
            total_failures=len(failures),
            by_category=_count(failure.category.value for failure in failures),
            by_provider=_count(failure.provider for failure in failures),
            by_severity=_count(failure.severity.value for failure in failures),
            top_suggested_actions=[
                action
                for action, _ in sorted(
                    actions.items(), key=lambda item: (-item[1], item[0])
                )[:5]
            ],
        )


class FailureReport(BaseModel):
    """Stable top-level artifact for benchmark failure analysis."""

    model_config = ConfigDict(extra="forbid")

    id: str
    benchmark: str
    run_id: str
    created_at: str
    failures: list[FailureCase] = Field(default_factory=list)
    summary: RootCauseSummary
    by_provider: dict[str, RootCauseSummary] = Field(default_factory=dict)
    mneno_only: RootCauseSummary | None = None
    baseline_only: RootCauseSummary | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def populate_provider_summaries(self) -> FailureReport:
        if not self.by_provider:
            providers = sorted({failure.provider for failure in self.failures})
            self.by_provider = {
                provider: RootCauseSummary.from_failures(
                    [
                        failure
                        for failure in self.failures
                        if failure.provider == provider
                    ]
                )
                for provider in providers
            }
        if self.mneno_only is None:
            self.mneno_only = RootCauseSummary.from_failures(
                [failure for failure in self.failures if failure.provider == "mneno"]
            )
        if self.baseline_only is None:
            self.baseline_only = RootCauseSummary.from_failures(
                [
                    failure
                    for failure in self.failures
                    if is_baseline_provider(failure.provider)
                ]
            )
        return self


def failure_report_summary(report: FailureReport) -> dict[str, Any]:
    """Return a stable dashboard/report summary without embedding run timestamps."""

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    worst = sorted(
        report.failures,
        key=lambda failure: (
            severity_rank[failure.severity.value],
            failure.case_id,
            failure.provider,
            failure.category.value,
        ),
    )[:10]
    top_categories = _top_categories(report.summary)
    mneno_summary = report.mneno_only or RootCauseSummary()
    baseline_summary = report.baseline_only or RootCauseSummary()
    return {
        "failure_count": report.summary.total_failures,
        "top_categories": top_categories,
        "top_categories_overall": top_categories,
        "top_categories_mneno": _top_categories(mneno_summary),
        "top_categories_baselines": _top_categories(baseline_summary),
        "top_suggested_actions": report.summary.top_suggested_actions,
        "mneno_suggested_actions": mneno_summary.top_suggested_actions,
        "baseline_suggested_actions": baseline_summary.top_suggested_actions,
        "worst_cases": [
            {
                "case_id": failure.case_id,
                "provider": failure.provider,
                "category": failure.category.value,
                "severity": failure.severity.value,
            }
            for failure in worst
        ],
    }


def _count(values: Any) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _top_categories(summary: RootCauseSummary) -> dict[str, int]:
    return dict(
        sorted(summary.by_category.items(), key=lambda item: (-item[1], item[0]))[:5]
    )


def is_baseline_provider(provider: str) -> bool:
    return provider in BASELINE_PROVIDERS or provider.endswith("_baseline")
