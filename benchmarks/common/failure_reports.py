"""JSON and Markdown writers for failure analysis artifacts."""

from __future__ import annotations

from pathlib import Path

from benchmarks.common.failures import FailureReport, RootCauseSummary
from benchmarks.common.utils import save_json


def write_failure_report_json(report: FailureReport, path: str | Path) -> Path:
    return save_json(path, report.model_dump(mode="json"))


def write_failure_dashboard_json(report: FailureReport, path: str | Path) -> Path:
    """Write compact summaries and worst cases for the static dashboard."""

    selected = {
        failure.id: failure
        for summary_failures in (
            _worst_failures(report)[:10],
            *(
                [
                    failure
                    for failure in _worst_failures(report)
                    if failure.provider == provider
                ][:10]
                for provider in report.by_provider
            ),
        )
        for failure in summary_failures
    }
    payload = report.model_dump(mode="json")
    payload["failures"] = [
        failure.model_dump(mode="json") for failure in selected.values()
    ]
    payload["metadata"] = {
        **payload["metadata"],
        "dashboard_projection": True,
        "full_failure_count": report.summary.total_failures,
    }
    return save_json(path, payload)


def write_failure_report_markdown(report: FailureReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Failure Analysis",
        "",
        f"- Benchmark: **{report.benchmark}**",
        f"- Run ID: `{report.run_id}`",
        f"- Total failures: **{report.summary.total_failures}**",
        "",
        "## Top Categories Overall",
        "",
        *_count_table(report.summary.by_category, "Category", ranked=True),
        "",
        "## Top Categories for Mneno",
        "",
        *_count_table(_summary(report.mneno_only).by_category, "Category", ranked=True),
        "",
        "## Top Categories for Baselines",
        "",
        *_count_table(
            _summary(report.baseline_only).by_category, "Category", ranked=True
        ),
        "",
        "## Failures by Provider",
        "",
        *_count_table(report.summary.by_provider, "Provider"),
        "",
        "## Failures by Severity",
        "",
        *_count_table(report.summary.by_severity, "Severity"),
        "",
        "## Provider Summaries",
        "",
    ]
    for provider, summary in sorted(report.by_provider.items()):
        lines.extend(
            [
                f"### {provider}",
                "",
                f"- Total failures: **{summary.total_failures}**",
                f"- Top categories: {_inline_counts(summary.by_category)}",
                "",
            ]
        )

    lines.extend(
        [
            "## Suggested Actions for Mneno",
            "",
        ]
    )
    mneno_actions = _summary(report.mneno_only).top_suggested_actions
    if mneno_actions:
        lines.extend(f"- {action}" for action in mneno_actions)
    else:
        lines.append("No Mneno failures were recorded.")

    lines.extend(
        [
            "",
            "## Baseline Comparison Evidence",
            "",
            "- Full Context including forbidden or stale memories is expected behavior because it intentionally includes everything; this is comparison evidence, not necessarily a bug.",
            "- Random retrieval failures are expected baseline behavior and provide a lower-bound comparison.",
            "- Keyword retrieval and session failures reflect known baseline limitations.",
            "",
        ]
    )
    baseline_actions = _summary(report.baseline_only).top_suggested_actions
    if baseline_actions:
        lines.extend(f"- {action}" for action in baseline_actions)
    else:
        lines.append("No baseline failures were recorded.")

    lines.extend(["", "## Top 10 Failure Cases", ""])
    if not report.failures:
        lines.append("No failures were recorded.")
    for failure in _worst_failures(report)[:10]:
        lines.extend(
            [
                f"### {failure.case_id} / {failure.provider} / {failure.category.value}",
                "",
                f"- Severity: **{failure.severity.value}**",
                f"- Interpretation: **{_failure_label(failure.expected_behavior)}**",
                f"- Reason: {failure.reason}",
                f"- Provider note: {failure.interpretation or 'No provider-specific note.'}",
                f"- Expected IDs: `{_ids(failure.expected_ids)}`",
                f"- Retrieved IDs: `{_ids(failure.retrieved_ids)}`",
                f"- Included IDs: `{_ids(failure.included_ids)}`",
                f"- Trace IDs: `{_ids(failure.trace_ids)}`",
                f"- Suggested action: {failure.suggested_action}",
                "",
            ]
        )
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return destination


def _count_table(values: dict[str, int], label: str, ranked: bool = False) -> list[str]:
    lines = [f"| {label} | Count |", "| --- | ---: |"]
    if not values:
        lines.append("| None | 0 |")
    else:
        entries = (
            sorted(values.items(), key=lambda item: (-item[1], item[0]))
            if ranked
            else list(values.items())
        )
        lines.extend(f"| {name} | {count} |" for name, count in entries)
    return lines


def _worst_failures(report: FailureReport):
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        report.failures,
        key=lambda failure: (
            severity_rank[failure.severity.value],
            failure.case_id,
            failure.provider,
            failure.category.value,
        ),
    )


def _ids(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _summary(value: RootCauseSummary | None) -> RootCauseSummary:
    return value or RootCauseSummary()


def _inline_counts(values: dict[str, int]) -> str:
    if not values:
        return "none"
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{name} ({count})" for name, count in ordered[:5])


def _failure_label(expected_behavior: bool) -> str:
    return "expected baseline behavior" if expected_behavior else "observed failure"
