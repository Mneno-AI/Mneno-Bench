"""Run Mneno Context Rot Suite v1 locally and deterministically."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from rich.console import Console

from benchmarks.common.baselines import (
    full_context_baseline,
    keyword_baseline,
    random_baseline,
)
from benchmarks.common.capabilities import detect_mneno_capabilities
from benchmarks.common.mneno_client import INSTALL_MESSAGE, MnenoAdapter
from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRun,
    MetricResult,
    MnenoDecisionSummary,
    MnenoResult,
    NormalizedSearchResult,
    RunStatus,
    TraceSummary,
)
from benchmarks.common.utils import estimate_tokens, generate_run_id, now_iso, save_json
from benchmarks.mneno_suite.dataset import (
    MnenoSuiteCase,
    MnenoSuiteDataset,
    load_mneno_suite_dataset,
)
from benchmarks.mneno_suite.metrics import (
    compaction_retention_score,
    context_efficiency_score,
    expected_memory_recall,
    explainability_coverage_score,
    forbidden_memory_error_rate,
    lifecycle_alignment_score,
    session_continuity_score,
    stale_memory_suppression_rate,
)
from benchmarks.mneno_suite.execution import (
    MnenoRuntime,
    execute_mneno_case,
    initialize_mneno_runtime,
)
from benchmarks.mneno_suite.scoring import (
    DEFAULT_CONTEXT_ROT_WEIGHTS,
    calculate_context_rot_score,
)

app = typer.Typer(add_completion=False)
console = Console()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_VERSION = "0.4.0"
SUITE_NAME = "Mneno Context Rot Suite v1"
SYSTEMS = ["keyword_baseline", "full_context_baseline", "random_baseline", "mneno"]

METRIC_DESCRIPTIONS = {
    "expected_memory_recall": "Expected memories retrieved divided by expected memories.",
    "stale_memory_suppression_rate": "Forbidden stale memories avoided divided by forbidden memories.",
    "forbidden_memory_error_rate": "Forbidden memories retrieved divided by forbidden memories.",
    "context_efficiency_score": "Useful expected-memory tokens divided by supplied context tokens.",
    "lifecycle_alignment_score": "Active evidence selected and inactive evidence avoided.",
    "session_continuity_score": "Current-session evidence selected and other-session conflicts avoided.",
    "compaction_retention_score": "Important expected memories retained after compaction.",
    "explainability_coverage_score": "Retrieved decisions covered by trace events, decisions, or reasons.",
}


def run_mneno_context_rot_suite(
    data_dir: Path,
    results_dir: Path,
    k: int = 4,
    adapter: MnenoAdapter | None = None,
) -> BenchmarkRun:
    dataset = load_mneno_suite_dataset(_resolve_suite_data_dir(data_dir))
    memories = [memory.as_benchmark_memory() for memory in dataset.memories]
    memory_by_id = dataset.memory_by_id
    sdk = adapter or MnenoAdapter()
    mneno_available = sdk.is_available()

    run = BenchmarkRun(
        benchmark_version=BENCHMARK_VERSION,
        mneno_version=sdk.version() if mneno_available else None,
        run_id=generate_run_id("context-rot-v1"),
        suite="mneno_context_rot_suite_v1",
        status=RunStatus.RUNNING,
        started_at=now_iso(),
        systems=SYSTEMS,
        config={
            "default_k": k,
            "data_source": "data/mneno_suite",
            "score_weights": DEFAULT_CONTEXT_ROT_WEIGHTS,
        },
        export_metadata={
            "format": "mneno-bench.context-rot",
            "suite_name": SUITE_NAME,
            "suite_version": 1,
            "run_timestamp": now_iso(),
        },
    )

    runtime: MnenoRuntime | None = None
    if mneno_available:
        runtime = initialize_mneno_runtime(sdk, dataset, results_dir, run.run_id)
        run.export_metadata["mneno_execution"] = runtime.summary.model_dump(mode="json")
    else:
        run.export_metadata["mneno_execution"] = {
            "memories_loaded": 0,
            "sessions_created": 0,
            "conflicts_detected": 0,
            "hierarchy_evaluated": False,
            "hierarchy_transitions": {},
            "compaction_previewed": False,
            "compaction_stats": {},
            "traces_exported": 0,
            "memory_id_map": {},
            "memory_loads": [],
            "capability_errors": {},
            "capability_report": detect_mneno_capabilities(sdk).model_dump(mode="json"),
        }

    case_metrics: dict[str, dict[str, dict[str, float | None]]] = defaultdict(dict)
    failure_cases: list[dict[str, Any]] = []

    for case in dataset.cases:
        limit = case.budget or k
        baseline_results: list[BaselineResult] = []
        metrics_by_system: dict[str, list[MetricResult]] = {}

        for name, baseline in (
            ("keyword_baseline", keyword_baseline),
            ("full_context_baseline", full_context_baseline),
            ("random_baseline", random_baseline),
        ):
            normalized = baseline(memories, case.query, k=limit)
            retrieved_ids = _retrieved_ids(normalized)
            values = _case_metric_values(
                case,
                retrieved_ids,
                retrieved_ids,
                memory_by_id,
                trace_summary=None,
            )
            case_metrics[name][case.id] = values
            metrics_by_system[name] = _metric_results(values)
            baseline_results.append(
                BaselineResult(
                    name=name,
                    retrieved_memory_ids=retrieved_ids,
                    context_tokens=_context_tokens(memories, retrieved_ids),
                    latency_ms=float(normalized.metrics.get("latency_ms") or 0.0),
                    metadata={
                        "category": case.category,
                        "normalized_result": normalized.model_dump(mode="json"),
                    },
                )
            )
            _record_failure(failure_cases, name, case, retrieved_ids)

        if not mneno_available:
            mneno_result = MnenoResult(
                status=RunStatus.SKIPPED,
                skip_reason=INSTALL_MESSAGE,
                metadata={"category": case.category},
            )
            metrics_by_system["mneno"] = []
        else:
            assert runtime is not None
            execution = execute_mneno_case(
                runtime,
                case,
                results_dir,
                run.run_id,
                max(k, limit),
            )
            mneno_result = execution.result
            mneno_result.context_tokens = _context_tokens(
                memories, execution.metric_ids
            )
            if mneno_result.status == RunStatus.COMPLETED:
                mneno_values = _case_metric_values(
                    case,
                    execution.metric_ids,
                    execution.compacted_ids,
                    memory_by_id,
                    mneno_result.trace_summary,
                    decision_summary=mneno_result.decision_summary,
                    hierarchy_available=execution.hierarchy_available,
                    session_context_available=execution.session_context_available,
                    explainability_available=execution.explainability_available,
                )
                case_metrics["mneno"][case.id] = mneno_values
                metrics_by_system["mneno"] = _metric_results(mneno_values)
                _record_failure(
                    failure_cases,
                    "mneno",
                    case,
                    mneno_result.retrieved_memory_ids,
                )
            else:
                metrics_by_system["mneno"] = []

        run.results.append(
            BenchmarkResult(
                case=_benchmark_case(case),
                baseline_results=baseline_results,
                mneno_result=mneno_result,
                metrics=metrics_by_system,
            )
        )

    suite_summary = _build_suite_summary(dataset, case_metrics, mneno_available)
    for system, summary in suite_summary["systems"].items():
        if summary["status"] == RunStatus.COMPLETED.value:
            run.summary_metrics[system] = _metric_results(summary["metrics"])
            run.summary_metrics[system].append(
                MetricResult(
                    name="context_rot_score",
                    value=summary["context_rot_score"],
                    description="Weighted Mneno Context Rot Score.",
                )
            )

    if runtime is not None:
        try:
            all_traces = sdk.export_all_traces(client=runtime.client)
            all_traces_path = (
                results_dir / "mneno" / "traces" / f"{run.run_id}-all.json"
            )
            save_json(all_traces_path, all_traces)
            run.export_metadata["all_traces"] = str(all_traces_path)
            runtime.summary.traces_exported += 1
        except (AttributeError, RuntimeError):
            pass
        run.export_metadata["mneno_execution"] = runtime.summary.model_dump(mode="json")

    report_path = results_dir / "reports" / "context_rot_suite_latest.md"
    result_path = results_dir / "mneno" / "context_rot_suite_latest.json"
    suite_summary["failure_cases"] = failure_cases
    suite_summary["report_path"] = str(report_path)
    suite_summary["result_path"] = str(result_path)
    suite_summary["trace_directory"] = str(results_dir / "mneno" / "traces")
    suite_summary["export_directory"] = str(results_dir / "mneno" / "exports")
    run.export_metadata["context_rot_suite"] = suite_summary
    run.export_metadata["mneno_status"] = (
        RunStatus.COMPLETED.value if mneno_available else RunStatus.SKIPPED.value
    )
    run.status = RunStatus.COMPLETED if not run.errors else RunStatus.FAILED
    run.finished_at = now_iso()

    save_json(result_path, run.model_dump(mode="json"))
    _write_report(run, report_path)
    console.print(f"[green]Result:[/green] {result_path}")
    console.print(f"[green]Report:[/green] {report_path}")
    if not mneno_available:
        console.print(
            "[yellow]Mneno SDK unavailable; Mneno results were skipped.[/yellow]"
        )
    return run


def run_demo(
    data_dir: Path,
    results_dir: Path,
    k: int = 4,
    adapter: MnenoAdapter | None = None,
) -> BenchmarkRun:
    """Backward-compatible entrypoint retained for scripts and Step 1/2 callers."""

    return run_mneno_context_rot_suite(data_dir, results_dir, k, adapter)


def _case_metric_values(
    case: MnenoSuiteCase,
    retrieved_ids: list[str],
    compacted_ids: list[str] | None,
    memory_by_id: Mapping[str, Any],
    trace_summary: TraceSummary | None,
    decision_summary: MnenoDecisionSummary | None = None,
    hierarchy_available: bool = True,
    session_context_available: bool = True,
    explainability_available: bool = True,
) -> dict[str, float | None]:
    return {
        "expected_memory_recall": expected_memory_recall(
            retrieved_ids, case.expected_memory_ids
        ),
        "stale_memory_suppression_rate": stale_memory_suppression_rate(
            retrieved_ids, case.forbidden_memory_ids
        ),
        "forbidden_memory_error_rate": forbidden_memory_error_rate(
            retrieved_ids, case.forbidden_memory_ids
        ),
        "context_efficiency_score": context_efficiency_score(
            retrieved_ids, case.expected_memory_ids, memory_by_id
        ),
        "lifecycle_alignment_score": (
            lifecycle_alignment_score(
                retrieved_ids,
                case.expected_memory_ids,
                case.forbidden_memory_ids,
                memory_by_id,
            )
            if hierarchy_available
            else None
        ),
        "session_continuity_score": (
            session_continuity_score(
                retrieved_ids,
                case.expected_memory_ids,
                case.forbidden_memory_ids,
                memory_by_id,
                case.current_session_id,
            )
            if session_context_available
            else None
        ),
        "compaction_retention_score": (
            compaction_retention_score(
                compacted_ids, case.expected_memory_ids, memory_by_id
            )
            if compacted_ids is not None
            else None
        ),
        "explainability_coverage_score": (
            explainability_coverage_score(
                retrieved_ids, trace_summary, decision_summary
            )
            if explainability_available
            else None
        ),
    }


def _build_suite_summary(
    dataset: MnenoSuiteDataset,
    case_metrics: Mapping[str, Mapping[str, Mapping[str, float | None]]],
    mneno_available: bool,
) -> dict[str, Any]:
    systems: dict[str, Any] = {}
    for system in SYSTEMS:
        values_by_case = case_metrics.get(system, {})
        if system == "mneno" and not mneno_available:
            systems[system] = {
                "status": RunStatus.SKIPPED.value,
                "skip_reason": INSTALL_MESSAGE,
                "context_rot_score": None,
                "metrics": {},
                "categories": {},
            }
            continue
        aggregate = _average_metric_maps(values_by_case.values())
        categories: dict[str, Any] = {}
        for category in sorted({case.category for case in dataset.cases}):
            category_ids = {
                case.id for case in dataset.cases if case.category == category
            }
            category_metrics = _average_metric_maps(
                values
                for case_id, values in values_by_case.items()
                if case_id in category_ids
            )
            categories[category] = {
                "case_count": len(category_ids),
                "context_rot_score": calculate_context_rot_score(category_metrics),
                "metrics": category_metrics,
            }
        systems[system] = {
            "status": RunStatus.COMPLETED.value,
            "context_rot_score": calculate_context_rot_score(aggregate),
            "metrics": aggregate,
            "categories": categories,
        }
    return {
        "dataset": {
            "memory_count": len(dataset.memories),
            "case_count": len(dataset.cases),
            "categories": sorted({case.category for case in dataset.cases}),
        },
        "weights": DEFAULT_CONTEXT_ROT_WEIGHTS,
        "systems": systems,
    }


def _average_metric_maps(values: Any) -> dict[str, float | None]:
    rows = list(values)
    if not rows:
        return {}
    names = sorted({name for row in rows for name in row})
    averaged: dict[str, float | None] = {}
    for name in names:
        available = [row.get(name) for row in rows if row.get(name) is not None]
        averaged[name] = (
            round(sum(float(value) for value in available) / len(available), 6)
            if available
            else None
        )
    return averaged


def _metric_results(values: Mapping[str, float | None]) -> list[MetricResult]:
    return [
        MetricResult(
            name=name,
            value=value,
            description=METRIC_DESCRIPTIONS.get(name, ""),
            unavailable_reason=(
                "Required Mneno capability or trace evidence was unavailable."
                if value is None
                else None
            ),
        )
        for name, value in sorted(values.items())
    ]


def _benchmark_case(case: MnenoSuiteCase) -> BenchmarkCase:
    return BenchmarkCase(
        id=case.id,
        query=case.query,
        expected_memory_ids=case.expected_memory_ids,
        stale_memory_ids=case.forbidden_memory_ids,
        tags=[case.category],
        metadata={
            "category": case.category,
            "forbidden_memory_ids": case.forbidden_memory_ids,
            "expected_behavior": case.expected_behavior,
            "budget": case.budget,
            "current_session_id": case.current_session_id,
            "notes": case.notes,
        },
    )


def _record_failure(
    failures: list[dict[str, Any]],
    system: str,
    case: MnenoSuiteCase,
    retrieved_ids: list[str],
) -> None:
    missing = sorted(set(case.expected_memory_ids) - set(retrieved_ids))
    forbidden = sorted(set(case.forbidden_memory_ids) & set(retrieved_ids))
    if missing or forbidden:
        failures.append(
            {
                "system": system,
                "case_id": case.id,
                "category": case.category,
                "missing_expected_ids": missing,
                "retrieved_forbidden_ids": forbidden,
            }
        )


def _write_report(run: BenchmarkRun, path: Path) -> None:
    suite = run.export_metadata["context_rot_suite"]
    systems = suite["systems"]
    lines = [
        f"# {SUITE_NAME}",
        "",
        f"- Run ID: `{run.run_id}`",
        f"- Status: **{run.status.value}**",
        f"- Benchmark version: **{run.benchmark_version}**",
        f"- Mneno version: **{run.mneno_version or 'not installed'}**",
        f"- Dataset: **{suite['dataset']['memory_count']} memories, {suite['dataset']['case_count']} cases**",
        "",
        "## Aggregate Scores",
        "",
        "| System | Status | Context Rot Score |",
        "| --- | --- | ---: |",
    ]
    for name in SYSTEMS:
        summary = systems[name]
        score = summary["context_rot_score"]
        display = "unavailable" if score is None else f"{score:.4f}"
        lines.append(f"| {name} | {summary['status']} | {display} |")

    lines.extend(["", "## Per-Category Scores", ""])
    completed = [name for name in SYSTEMS if systems[name]["status"] == "completed"]
    lines.append("| Category | " + " | ".join(completed) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in completed) + " |")
    for category in suite["dataset"]["categories"]:
        values = [
            _format_score(systems[name]["categories"][category]["context_rot_score"])
            for name in completed
        ]
        lines.append(f"| {category} | " + " | ".join(values) + " |")

    lines.extend(["", "## Aggregate Metrics", ""])
    lines.append("| System | Metric | Value |")
    lines.append("| --- | --- | ---: |")
    for name in completed:
        for metric, value in systems[name]["metrics"].items():
            lines.append(f"| {name} | {metric} | {_format_score(value)} |")

    execution = run.export_metadata.get("mneno_execution", {})
    capability_report = execution.get("capability_report", {})
    capabilities = capability_report.get("capabilities", {})
    lines.extend(
        [
            "",
            "## Mneno Core Execution",
            "",
            f"- Installed: **{'yes' if capability_report.get('available') else 'no'}**",
            f"- Partial capability support: **{'yes' if capability_report.get('partial') else 'no'}**",
            f"- Memories loaded: **{execution.get('memories_loaded', 0)}**",
            f"- Sessions created: **{execution.get('sessions_created', 0)}**",
            f"- Conflicts detected: **{execution.get('conflicts_detected', 0)}**",
            f"- Hierarchy evaluated: **{'yes' if execution.get('hierarchy_evaluated') else 'no'}**",
            f"- Compaction previewed: **{'yes' if execution.get('compaction_previewed') else 'no'}**",
            f"- Traces exported: **{execution.get('traces_exported', 0)}**",
            "",
            "### Capabilities",
            "",
            "| Capability | Supported |",
            "| --- | --- |",
        ]
    )
    for capability, supported in sorted(capabilities.items()):
        lines.append(f"| {capability} | {'yes' if supported else 'no'} |")
    missing = capability_report.get("missing", [])
    if missing:
        lines.extend(["", f"Missing capabilities: `{', '.join(missing)}`"])
    capability_errors = execution.get("capability_errors", {})
    if capability_errors:
        lines.extend(["", "### Capability Errors", ""])
        for capability, error in sorted(capability_errors.items()):
            lines.append(f"- `{capability}`: {error}")
    transitions = execution.get("hierarchy_transitions", {})
    if transitions:
        lines.extend(["", "Hierarchy transitions:"])
        for name, count in sorted(transitions.items()):
            lines.append(f"- {name}: **{count}**")
    compaction_stats = execution.get("compaction_stats", {})
    if compaction_stats:
        lines.extend(["", "Compaction preview stats:"])
        for name, count in sorted(compaction_stats.items()):
            lines.append(f"- {name}: **{count}**")

    lines.extend(["", "## Export Locations", ""])
    lines.append(f"- Result: `{suite['result_path']}`")
    lines.append(f"- Raw benchmark exports: `{suite['export_directory']}`")
    lines.append(f"- Raw traces: `{suite['trace_directory']}`")
    lines.extend(["", "## Failure Cases", ""])
    if not suite["failure_cases"]:
        lines.append("No expected-memory or forbidden-memory failures were recorded.")
    else:
        lines.append(
            "| System | Case | Category | Missing expected | Retrieved forbidden |"
        )
        lines.append("| --- | --- | --- | --- | --- |")
        for failure in suite["failure_cases"]:
            lines.append(
                f"| {failure['system']} | {failure['case_id']} | {failure['category']} | "
                f"{', '.join(failure['missing_expected_ids']) or '-'} | "
                f"{', '.join(failure['retrieved_forbidden_ids']) or '-'} |"
            )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This is a deterministic synthetic Mneno-specific benchmark.",
            "- No LLM judge, external API, or external dataset is used.",
            "- A skipped Mneno score means the optional SDK was unavailable; no score was fabricated.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _format_score(value: Any) -> str:
    return "unavailable" if value is None else f"{float(value):.4f}"


def _retrieved_ids(result: NormalizedSearchResult) -> list[str]:
    return _ids_from_raw(result.raw_result)


def _ids_from_raw(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        for key in (
            "retrieved_memory_ids",
            "compacted_memory_ids",
            "retained_memory_ids",
            "memory_ids",
            "ids",
        ):
            value = raw.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
        nested = raw.get("result") or raw.get("results") or raw.get("memories")
        if isinstance(nested, list):
            return _ids_from_items(nested)
    if isinstance(raw, list):
        return _ids_from_items(raw)
    return []


def _ids_from_items(items: list[Any]) -> list[str]:
    ids: list[str] = []
    for item in items:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            value = item.get("id") or item.get("memory_id")
            if value is not None:
                ids.append(str(value))
    return ids


def _context_tokens(memories: list[dict[str, Any]], memory_ids: list[str]) -> int:
    selected = set(memory_ids)
    return sum(
        estimate_tokens(str(memory.get("content", memory.get("text", ""))))
        for memory in memories
        if str(memory["id"]) in selected
    )


def _resolve_suite_data_dir(data_dir: Path) -> Path:
    nested = data_dir / "mneno_suite"
    return nested if nested.exists() else data_dir


@app.command()
def main(
    data_dir: Path | None = typer.Option(None, help="Benchmark data root."),
    results_dir: Path | None = typer.Option(None, help="Result output root."),
    k: int = typer.Option(4, min=1, help="Default retrieval depth."),
) -> None:
    """Run Mneno Context Rot Suite v1."""

    load_dotenv(PROJECT_ROOT / ".env")
    resolved_data = data_dir or PROJECT_ROOT / os.getenv("DATA_DIR", "data")
    resolved_results = results_dir or PROJECT_ROOT / os.getenv("RESULTS_DIR", "results")
    run_mneno_context_rot_suite(resolved_data, resolved_results, k=k)


if __name__ == "__main__":
    app()
