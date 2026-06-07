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
from benchmarks.common.mneno_client import INSTALL_MESSAGE, MnenoAdapter
from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRun,
    MetricResult,
    MnenoResult,
    NormalizedSearchResult,
    RunStatus,
    TraceSummary,
)
from benchmarks.common.traces import TraceLoader
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
from benchmarks.mneno_suite.scoring import (
    DEFAULT_CONTEXT_ROT_WEIGHTS,
    calculate_context_rot_score,
)

app = typer.Typer(add_completion=False)
console = Console()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_VERSION = "0.3.0"
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

    client: Any | None = None
    if mneno_available:
        client = sdk.create_client(trace_enabled=True)
        for memory in memories:
            sdk.add_memory(client, memory)

    case_metrics: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    failure_cases: list[dict[str, Any]] = []
    trace_loader = TraceLoader()

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
            mneno_result, mneno_values = _run_mneno_case(
                sdk,
                client,
                case,
                memories,
                memory_by_id,
                results_dir,
                run.run_id,
                trace_loader,
                limit,
            )
            if mneno_values is not None:
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
                if mneno_result.error:
                    run.errors.append(f"{case.id}: {mneno_result.error}")

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

    if mneno_available and client is not None:
        try:
            all_traces = sdk.export_all_traces(client=client)
            all_traces_path = (
                results_dir / "mneno" / "traces" / f"{run.run_id}-all.json"
            )
            save_json(all_traces_path, all_traces)
            run.export_metadata["all_traces"] = str(all_traces_path)
        except Exception as exc:
            run.errors.append(f"all trace export: {exc}")

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


def _run_mneno_case(
    sdk: MnenoAdapter,
    client: Any,
    case: MnenoSuiteCase,
    memories: list[dict[str, Any]],
    memory_by_id: Mapping[str, Any],
    results_dir: Path,
    run_id: str,
    trace_loader: TraceLoader,
    limit: int,
) -> tuple[MnenoResult, dict[str, float] | None]:
    try:
        common = {
            "client": client,
            "query": case.query,
            "expected_memory_ids": case.expected_memory_ids,
            "forbidden_memory_ids": case.forbidden_memory_ids,
            "current_session_id": case.current_session_id,
            "limit": limit,
            "k": limit,
        }
        search = sdk.evaluate_search(**common)
        context = None
        if case.category in {"context_budget", "session_continuity", "explainability"}:
            context = sdk.evaluate_context(**common)
        compaction = None
        if case.category == "compaction_retention":
            compaction = sdk.evaluate_compaction(**common)

        retrieved_ids = _retrieved_ids(search)
        compacted_ids = (
            _ids_from_raw(compaction.raw_result) if compaction else retrieved_ids
        )
        trace_id = search.trace_id
        if context is not None:
            trace_id = trace_id or context.trace_id
        if compaction is not None:
            trace_id = trace_id or compaction.trace_id

        trace_summary = None
        trace_path: Path | None = None
        if trace_id:
            trace_export = sdk.export_trace(trace_id=trace_id, client=client)
            trace_path = results_dir / "mneno" / "traces" / f"{run_id}-{case.id}.json"
            save_json(trace_path, trace_export)
            if (
                isinstance(trace_export, dict)
                and trace_export.get("format") == "mneno.trace"
            ):
                trace_summary = trace_loader.load_trace_export(trace_export)
                trace_summary.raw_trace_reference = str(trace_path)

        benchmark_export = sdk.export_benchmark(
            result=search.raw_result,
            evaluation=search.raw_result,
            client=client,
        )
        export_path = results_dir / "mneno" / "exports" / f"{run_id}-{case.id}.json"
        save_json(export_path, benchmark_export)
        values = _case_metric_values(
            case,
            retrieved_ids,
            compacted_ids,
            memory_by_id,
            trace_summary,
        )
        return (
            MnenoResult(
                status=RunStatus.COMPLETED,
                retrieved_memory_ids=retrieved_ids,
                context_tokens=_context_tokens(memories, retrieved_ids),
                latency_ms=float(search.metrics.get("latency_ms") or 0.0),
                trace_summary=trace_summary,
                metadata={
                    "category": case.category,
                    "benchmark_export": str(export_path),
                    "trace_export": str(trace_path) if trace_path else None,
                    "search_evaluation": search.model_dump(mode="json"),
                    "context_evaluation": context.model_dump(mode="json")
                    if context
                    else None,
                    "compaction_evaluation": (
                        compaction.model_dump(mode="json") if compaction else None
                    ),
                    "compacted_memory_ids": compacted_ids,
                },
            ),
            values,
        )
    except Exception as exc:
        return MnenoResult(status=RunStatus.FAILED, error=str(exc)), None


def _case_metric_values(
    case: MnenoSuiteCase,
    retrieved_ids: list[str],
    compacted_ids: list[str],
    memory_by_id: Mapping[str, Any],
    trace_summary: TraceSummary | None,
) -> dict[str, float]:
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
        "lifecycle_alignment_score": lifecycle_alignment_score(
            retrieved_ids,
            case.expected_memory_ids,
            case.forbidden_memory_ids,
            memory_by_id,
        ),
        "session_continuity_score": session_continuity_score(
            retrieved_ids,
            case.expected_memory_ids,
            case.forbidden_memory_ids,
            memory_by_id,
            case.current_session_id,
        ),
        "compaction_retention_score": compaction_retention_score(
            compacted_ids, case.expected_memory_ids, memory_by_id
        ),
        "explainability_coverage_score": explainability_coverage_score(
            retrieved_ids, trace_summary
        ),
    }


def _build_suite_summary(
    dataset: MnenoSuiteDataset,
    case_metrics: Mapping[str, Mapping[str, Mapping[str, float]]],
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


def _average_metric_maps(values: Any) -> dict[str, float]:
    rows = list(values)
    if not rows:
        return {}
    names = sorted({name for row in rows for name in row})
    return {
        name: round(sum(row.get(name, 0.0) for row in rows) / len(rows), 6)
        for name in names
    }


def _metric_results(values: Mapping[str, float]) -> list[MetricResult]:
    return [
        MetricResult(
            name=name,
            value=value,
            description=METRIC_DESCRIPTIONS.get(name, ""),
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
            f"{systems[name]['categories'][category]['context_rot_score']:.4f}"
            for name in completed
        ]
        lines.append(f"| {category} | " + " | ".join(values) + " |")

    lines.extend(["", "## Aggregate Metrics", ""])
    lines.append("| System | Metric | Value |")
    lines.append("| --- | --- | ---: |")
    for name in completed:
        for metric, value in systems[name]["metrics"].items():
            lines.append(f"| {name} | {metric} | {value:.4f} |")

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
