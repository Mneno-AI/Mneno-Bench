from benchmarks.common.failures import (
    FailureCase,
    FailureCategory,
    FailureReport,
    FailureSeverity,
    RootCauseSummary,
)


def _failure(
    category: FailureCategory = FailureCategory.RETRIEVAL_FAILURE,
    provider: str = "mneno",
    severity: FailureSeverity = FailureSeverity.HIGH,
    action: str = "Inspect retrieval.",
) -> FailureCase:
    return FailureCase(
        id=f"suite:case:{provider}:{category.value}",
        benchmark="suite",
        case_id="case",
        provider=provider,
        category=category,
        severity=severity,
        query="What changed?",
        expected_ids=["expected"],
        retrieved_ids=[],
        included_ids=[],
        excluded_ids=[],
        forbidden_ids=[],
        trace_ids=[],
        reason="Expected evidence was missing.",
        evidence=["missing_expected_ids=expected"],
        suggested_action=action,
    )


def test_failure_models_serialize_and_deserialize() -> None:
    failure = _failure()
    report = FailureReport(
        id="failures-run-1",
        benchmark="suite",
        run_id="run-1",
        created_at="2026-06-09T00:00:00Z",
        failures=[failure],
        summary=RootCauseSummary.from_failures([failure]),
    )

    restored = FailureReport.model_validate_json(report.model_dump_json())

    assert restored == report
    assert restored.failures[0].category == FailureCategory.RETRIEVAL_FAILURE


def test_root_cause_summary_aggregates_and_ranks_actions() -> None:
    failures = [
        _failure(action="Inspect retrieval."),
        _failure(provider="keyword", action="Inspect retrieval."),
        _failure(
            category=FailureCategory.JUDGE_FAILURE,
            severity=FailureSeverity.LOW,
            action="Inspect judge output.",
        ),
    ]

    summary = RootCauseSummary.from_failures(failures)

    assert summary.total_failures == 3
    assert summary.by_category == {"judge_failure": 1, "retrieval_failure": 2}
    assert summary.by_provider == {"keyword": 1, "mneno": 2}
    assert summary.by_severity == {"high": 2, "low": 1}
    assert summary.top_suggested_actions == [
        "Inspect retrieval.",
        "Inspect judge output.",
    ]


def test_failure_report_builds_provider_specific_summaries() -> None:
    failures = [
        *[
            _failure(
                category=FailureCategory.CONFLICT_RESOLUTION_FAILURE,
                provider="full_context_baseline",
                action="Comparison evidence.",
            )
            for _ in range(4)
        ],
        _failure(
            category=FailureCategory.CONTEXT_BUDGET_FAILURE,
            provider="mneno",
            action="Mneno Core: inspect budget.",
        ),
        _failure(provider="keyword_baseline", action="Comparison evidence."),
    ]
    report = FailureReport(
        id="provider-aware",
        benchmark="suite",
        run_id="run",
        created_at="2026-06-09T00:00:00Z",
        failures=failures,
        summary=RootCauseSummary.from_failures(failures),
    )

    assert report.summary.by_category["conflict_resolution_failure"] == 4
    assert report.by_provider["full_context_baseline"].total_failures == 4
    assert report.mneno_only is not None
    assert report.mneno_only.by_category == {"context_budget_failure": 1}
    assert report.baseline_only is not None
    assert report.baseline_only.total_failures == 5
    assert "conflict_resolution_failure" not in report.mneno_only.by_category
