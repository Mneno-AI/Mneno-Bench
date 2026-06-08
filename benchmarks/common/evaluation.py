"""Validation and conversion for Mneno benchmark result v1 exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRun,
    MetricResult,
    MnenoResult,
    RunStatus,
)
from benchmarks.common.utils import generate_run_id, load_json, now_iso


class EvaluationExport(BaseModel):
    """Validated mneno.benchmark.result v1 envelope."""

    model_config = ConfigDict(extra="allow")

    format: str
    version: int


class EvaluationLoader:
    """Load a Mneno benchmark export and normalize it into durable run models."""

    def load(
        self, source: str | Path | dict[str, Any]
    ) -> tuple[BenchmarkRun, list[BenchmarkResult]]:
        payload = load_json(source) if isinstance(source, (str, Path)) else source
        export = EvaluationExport.model_validate(payload)
        if export.format != "mneno.benchmark.result":
            raise ValueError(
                "Evaluation export format must be 'mneno.benchmark.result'."
            )
        if export.version != 1:
            raise ValueError(
                f"Unsupported mneno.benchmark.result version: {export.version}"
            )
        run = self._to_run(payload)
        return run, run.results

    def load_export(
        self, source: str | Path | dict[str, Any]
    ) -> tuple[BenchmarkRun, list[BenchmarkResult]]:
        return self.load(source)

    def _to_run(self, payload: dict[str, Any]) -> BenchmarkRun:
        embedded = payload.get("run")
        if isinstance(embedded, Mapping):
            run = BenchmarkRun.model_validate(embedded)
            run.export_metadata.setdefault("raw_benchmark_export", payload)
            return run

        raw_results = payload.get("results") or payload.get("cases") or []
        results = [
            self._to_result(item, index)
            for index, item in enumerate(raw_results)
            if isinstance(item, Mapping)
        ]
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, Mapping):
            metadata = {}
        return BenchmarkRun(
            schema_version=str(payload.get("schema_version", "1.0")),
            benchmark_version=str(
                payload.get(
                    "benchmark_version", metadata.get("benchmark_version", "0.2.0")
                )
            ),
            mneno_version=_optional_string(
                payload.get("mneno_version", metadata.get("mneno_version"))
            ),
            run_id=str(payload.get("run_id") or generate_run_id("mneno-import")),
            suite=str(payload.get("suite") or payload.get("benchmark") or "mneno"),
            status=_status(payload.get("status", "completed")),
            started_at=str(
                payload.get("started_at") or payload.get("timestamp") or now_iso()
            ),
            finished_at=_optional_string(payload.get("finished_at")),
            systems=[str(item) for item in payload.get("systems", ["mneno"])],
            config=dict(payload.get("config", {})),
            results=results,
            summary_metrics=_metrics_by_system(payload.get("summary_metrics", {})),
            errors=[str(item) for item in payload.get("errors", [])],
            export_metadata={
                "format": "mneno.benchmark.result",
                "version": 1,
                "raw_benchmark_export": payload,
            },
        )

    def _to_result(self, item: Mapping[str, Any], index: int) -> BenchmarkResult:
        raw_case = item.get("case")
        if isinstance(raw_case, Mapping):
            case = BenchmarkCase.model_validate(raw_case)
        else:
            case = BenchmarkCase(
                id=str(item.get("case_id") or item.get("id") or f"case-{index + 1}"),
                query=str(item.get("query", "")),
                expected_memory_ids=_strings(item.get("expected_memory_ids", [])),
                stale_memory_ids=_strings(item.get("stale_memory_ids", [])),
            )

        raw_mneno = item.get("mneno_result")
        if isinstance(raw_mneno, Mapping):
            mneno_result = MnenoResult.model_validate(raw_mneno)
        else:
            raw_output = item.get("result") or item.get("output") or item
            output = raw_output if isinstance(raw_output, Mapping) else {}
            mneno_result = MnenoResult(
                status=_status(output.get("status", "completed")),
                retrieved_memory_ids=_strings(
                    output.get("retrieved_memory_ids")
                    or output.get("memory_ids")
                    or output.get("ids")
                    or []
                ),
                context_tokens=int(output.get("context_tokens", 0)),
                latency_ms=float(output.get("latency_ms", 0.0)),
                metadata={"raw_result": dict(output)},
            )

        baseline_results = [
            BaselineResult.model_validate(value)
            for value in item.get("baseline_results", [])
            if isinstance(value, Mapping)
        ]
        return BenchmarkResult(
            case=case,
            baseline_results=baseline_results,
            mneno_result=mneno_result,
            metrics=_metrics_by_system(item.get("metrics", {"mneno": {}})),
        )


def _metrics_by_system(value: Any) -> dict[str, list[MetricResult]]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, list[MetricResult]] = {}
    for system, raw_metrics in value.items():
        if isinstance(raw_metrics, Mapping):
            normalized[str(system)] = [
                MetricResult(
                    name=str(name),
                    value=float(
                        metric.get("value", 0.0)
                        if isinstance(metric, Mapping)
                        else metric
                    ),
                    unit=str(metric.get("unit", "ratio"))
                    if isinstance(metric, Mapping)
                    else "ratio",
                    description=str(metric.get("description", ""))
                    if isinstance(metric, Mapping)
                    else "",
                )
                for name, metric in raw_metrics.items()
                if isinstance(metric, (int, float, Mapping))
            ]
        elif isinstance(raw_metrics, list):
            normalized[str(system)] = [
                MetricResult.model_validate(metric)
                for metric in raw_metrics
                if isinstance(metric, Mapping)
            ]
    return normalized


def _status(value: Any) -> RunStatus:
    try:
        return RunStatus(str(value))
    except ValueError:
        return RunStatus.FAILED


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None
