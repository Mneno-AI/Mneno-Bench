import json
from pathlib import Path

from benchmarks.common.failure_reports import (
    write_failure_dashboard_json,
    write_failure_report_json,
    write_failure_report_markdown,
)
from benchmarks.common.failures import (
    FailureCase,
    FailureCategory,
    FailureReport,
    FailureSeverity,
    RootCauseSummary,
)


def test_failure_report_writers_create_json_and_markdown(tmp_path: Path) -> None:
    failure = FailureCase(
        id="suite:case:mneno:retrieval_failure",
        benchmark="suite",
        case_id="case",
        provider="mneno",
        category=FailureCategory.RETRIEVAL_FAILURE,
        severity=FailureSeverity.HIGH,
        query="Where is the fact?",
        expected_ids=["m1"],
        reason="Expected evidence was missing.",
        evidence=["missing_expected_ids=m1"],
        suggested_action="Inspect retrieval.",
    )
    report = FailureReport(
        id="run-failures",
        benchmark="suite",
        run_id="run",
        created_at="2026-06-09T00:00:00Z",
        failures=[failure],
        summary=RootCauseSummary.from_failures([failure]),
    )

    json_path = write_failure_report_json(report, tmp_path / "failures.json")
    markdown_path = write_failure_report_markdown(report, tmp_path / "failures.md")

    assert json_path.exists()
    assert markdown_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Failure Analysis" in markdown
    assert "retrieval_failure" in markdown
    assert "Expected IDs: `m1`" in markdown
    assert "## Top Categories Overall" in markdown
    assert "## Top Categories for Mneno" in markdown
    assert "## Top Categories for Baselines" in markdown
    assert "## Baseline Comparison Evidence" in markdown
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["by_provider"]["mneno"]["total_failures"] == 1
    assert payload["mneno_only"]["total_failures"] == 1
    assert payload["baseline_only"]["total_failures"] == 0

    dashboard_path = write_failure_dashboard_json(
        report, tmp_path / "dashboard-failures.json"
    )
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["summary"]["total_failures"] == 1
    assert dashboard["metadata"]["dashboard_projection"] is True
    assert dashboard["metadata"]["full_failure_count"] == 1
