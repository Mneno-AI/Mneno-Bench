"""Run the external LOCOMO benchmark pipeline without fabricating QA scores."""

from __future__ import annotations

import multiprocessing
import os
import re
import time
from collections import Counter, defaultdict
from collections.abc import Mapping
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import dataclass
from queue import Empty
from pathlib import Path
from threading import Lock
from typing import Any, Callable

import typer
from dotenv import load_dotenv
from rich.console import Console

from benchmarks.common.baselines import full_context_baseline, keyword_baseline
from benchmarks.common.failure_reports import (
    write_failure_dashboard_json,
    write_failure_report_json,
    write_failure_report_markdown,
)
from benchmarks.common.llm_client import (
    CachedRerankerProvider,
    LLMClient,
    LLMConfig,
)
from benchmarks.common.mneno_client import INSTALL_MESSAGE, MnenoAdapter
from benchmarks.common.schema import (
    BaselineResult,
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRun,
    MetricResult,
    MnenoResult,
    NormalizedContextResult,
    NormalizedSearchResult,
    RunStatus,
    TraceSummary,
)
from benchmarks.common.traces import TraceLoader
from benchmarks.common.utils import estimate_tokens, generate_run_id, now_iso, save_json
from benchmarks.locomo.checkpoints import (
    CheckpointCompatibilityError,
    LOCOMOCaseCheckpointStore,
    locomo_checkpoint_fingerprint,
)
from benchmarks.locomo.answering import AnswerCandidate, generate_answer_from_context
from benchmarks.locomo.config import (
    LOCOMOExecutionPhase,
    LOCOMOEvaluationConfig,
    LOCOMOEvaluationMode,
)
from benchmarks.locomo.deep_dive import (
    DEFAULT_SAMPLE_SIZE,
    analyze_retrieval_failures,
    write_retrieval_deep_dive,
)
from benchmarks.locomo.judge import JudgeResult, LOCOMOJudge
from benchmarks.locomo.failure_analysis import (
    analyze_locomo_failures,
    locomo_failure_report_summary,
)
from benchmarks.locomo.loader import load_locomo_dataset
from benchmarks.locomo.metrics import (
    OFFICIAL_SCORING_PENDING,
    aggregate_metric_maps,
    answer_diagnostic_score,
    contains_answer,
    evidence_precision,
    evidence_recall,
    exact_match,
    normalized_exact_match,
    official_locomo_qa_score,
    official_metric_placeholders,
    retrieval_hit_rate,
    token_f1,
)
from benchmarks.locomo.normalization import NormalizedLOCOMOResult
from benchmarks.locomo.schema import LOCOMOConversation, LOCOMODataset, LOCOMOQuestion
from benchmarks.locomo.validator import LOCOMODatasetMissingError
from benchmarks.locomo.validator import locomo_validation_warnings

app = typer.Typer(add_completion=False)
console = Console()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_VERSION = "0.6.0"
SUITE_NAME = "LOCOMO"
SYSTEMS = ["keyword_baseline", "full_context_baseline", "mneno"]
CATEGORY_NAMES = {
    1: "factual_recall",
    2: "temporal_reasoning",
    3: "multi_hop_reasoning",
    4: "open_domain",
    5: "adversarial",
}


@dataclass
class _ConversationOutcome:
    index: int
    results: list[BenchmarkResult]
    metrics_by_system: dict[str, list[dict[str, float | int | None]]]
    judge_status_by_system: dict[str, list[str]]
    trace_ids_by_system: dict[str, list[str]]
    system_errors: dict[str, list[str]]
    reranker_stats: dict[str, int]

    @property
    def case_count(self) -> int:
        return len(self.results)


class _CaseProgress:
    """Thread-safe, case-level progress shared by serial and parallel runners."""

    def __init__(self, total: int, started_at: float, initial_completed: int = 0) -> None:
        self.total = total
        self.started_at = started_at
        self.completed = min(initial_completed, total)
        self._lock = Lock()

    def advance(self, count: int = 1) -> None:
        with self._lock:
            self.completed = min(self.completed + count, self.total)
            if _should_report_progress(self.completed, self.total):
                _report_progress(self.completed, self.total, self.started_at)


def run_locomo(
    data_dir: Path,
    results_dir: Path,
    k: int = 5,
    adapter: MnenoAdapter | None = None,
    config_path: Path | None = None,
    evaluation_config: LOCOMOEvaluationConfig | None = None,
    judge: LOCOMOJudge | None = None,
) -> BenchmarkRun:
    """Execute LOCOMO loading, retrieval, normalization, and reporting."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    config = _load_config(config_path, k, evaluation_config)
    run = _new_run(config, adapter)
    result_path = results_dir / "locomo" / "locomo_latest.json"
    report_path = results_dir / "locomo" / "locomo_latest.md"

    try:
        dataset = load_locomo_dataset(
            _resolve_data_dir(data_dir),
            allow_malformed_evidence=config.allow_malformed_evidence,
        )
    except LOCOMODatasetMissingError as exc:
        return _finish_missing_dataset(run, result_path, report_path, str(exc))

    sdk = adapter or MnenoAdapter()
    mneno_available = sdk.is_available()
    if mneno_available:
        run.mneno_version = sdk.version()
    reranker_stats: Counter[str] = Counter()
    validation_warnings = _validation_warnings(dataset)
    jobs = _conversation_jobs(dataset, config.max_cases)
    all_questions = [question for _, _, questions in jobs for question in questions]
    total_cases = len(all_questions)
    checkpoint_store = _checkpoint_store(dataset, config, results_dir, run, k)
    resumed_results: dict[str, BenchmarkResult] = {}
    if config.resume:
        checkpoint_store.validate_for_resume()
        resumed_results = checkpoint_store.load_cases(
            include_failed=config.reuse_failed_checkpoints,
            require_evaluation_fingerprint=(
                config.mode == "llm_judge" and config.phase == "full"
            ),
        )
    checkpoint_store.write_manifest(
        _checkpoint_manifest_metadata(dataset, config, run, k, checkpoint_store)
    )
    if config.phase == "evaluate_only":
        missing = [
            question.id for question in all_questions if question.id not in resumed_results
        ]
        if missing:
            raise CheckpointCompatibilityError(
                "Evaluate-only phase requires completed prediction checkpoints; "
                f"missing {len(missing)} case(s)."
            )
        locomo_judge = judge or _build_judge(config, results_dir, run.run_id)
        resumed_results = _evaluate_resumed_predictions(
            jobs,
            resumed_results,
            config,
            locomo_judge,
            results_dir,
            run.run_id,
            checkpoint_store,
        )
        executable_jobs: list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]] = []
    else:
        resumed_case_ids = set(resumed_results)
        executable_jobs = _filter_resumed_jobs(jobs, resumed_case_ids)
    effective_workers = min(config.workers, len(executable_jobs)) if executable_jobs else 1
    if effective_workers == 1:
        backend = "serial"
    elif _uses_external_requests(config) or adapter is not None or judge is not None:
        # External LiteLLM calls use a thread-shared global limiter. Avoid
        # uncoordinated per-process provider clients for NIM/judge traffic.
        backend = "thread"
    else:
        backend = "process"
    locomo_judge = (
        None
        if backend == "process"
        else judge or _build_judge(config, results_dir, run.run_id)
    )
    run.export_metadata["execution"] = _execution_metadata(
        config.workers, effective_workers, backend, resumed_cases=len(resumed_results)
    )
    run.export_metadata["checkpointing"] = {
        "enabled": True,
        "resume_requested": config.resume,
        "resumed_cases": len(resumed_results),
        "reuse_failed_checkpoints": config.reuse_failed_checkpoints,
        "checkpoint_dir": str(checkpoint_store.directory),
        "fingerprint": checkpoint_store.fingerprint,
        "evaluation_fingerprint": checkpoint_store.evaluation_fingerprint,
        "phase": config.phase,
    }
    llm_stats_before = LLMClient.global_stats()
    progress_started_at = time.monotonic()
    console.print(
        f"[cyan]LOCOMO:[/cyan] {len(resumed_results)}/{total_cases} cases | "
        f"mode={config.mode} | phase={config.phase} | "
        f"workers={effective_workers} ({backend}) | ETA calculating"
    )
    outcomes = _execute_conversation_jobs(
        jobs=executable_jobs,
        sdk=sdk,
        mneno_available=mneno_available,
        results_dir=results_dir,
        run_id=run.run_id,
        k=k,
        config=config,
        judge=locomo_judge,
        backend=backend,
        workers=effective_workers,
        total_cases=total_cases,
        progress_started_at=progress_started_at,
        initial_completed=len(resumed_results),
        checkpoint_dir=checkpoint_store.directory,
        checkpoint_fingerprint=checkpoint_store.fingerprint,
    )
    new_results = [
        result
        for outcome in sorted(outcomes, key=lambda item: item.index)
        for result in outcome.results
    ]
    for outcome in outcomes:
        reranker_stats.update(outcome.reranker_stats)
    results_by_id = {**resumed_results, **{result.case.id: result for result in new_results}}
    run.results = [
        results_by_id[question.id]
        for question in all_questions
        if question.id in results_by_id
    ]
    metrics_by_system, judge_status_by_system, trace_ids_by_system, system_errors = (
        _collect_result_facts(run.results)
    )

    run.export_metadata["mneno_reranker"] = _reranker_run_metadata(
        config, reranker_stats
    )
    run.export_metadata["external_requests"] = _stats_delta(
        llm_stats_before, LLMClient.global_stats()
    )

    summary = _build_summary(
        dataset,
        metrics_by_system,
        trace_ids_by_system,
        judge_status_by_system,
        system_errors,
        mneno_available,
        config,
        validation_warnings,
        result_path,
        report_path,
        run,
    )
    run.export_metadata["locomo"] = summary
    run.export_metadata["mneno_status"] = summary["systems"]["mneno"]["status"]
    for system, metric_rows in metrics_by_system.items():
        run.summary_metrics[system] = _metric_results(
            aggregate_metric_maps(metric_rows)
        )
    if not mneno_available:
        run.summary_metrics["mneno"] = official_metric_placeholders()
    run.status = RunStatus.COMPLETED
    run.finished_at = now_iso()
    _write_failure_analysis(run, results_dir, dataset)
    _write_dashboard_run(run, results_dir)
    save_json(result_path, run.model_dump(mode="json"))
    _write_report(run, report_path)
    console.print(f"[green]Result:[/green] {result_path}")
    console.print(f"[green]Report:[/green] {report_path}")
    return run


def _new_run(
    config: LOCOMOEvaluationConfig, adapter: MnenoAdapter | None = None
) -> BenchmarkRun:
    sdk = adapter or MnenoAdapter()
    available = sdk.is_available()
    return BenchmarkRun(
        benchmark_version=BENCHMARK_VERSION,
        mneno_version=sdk.version() if available else None,
        run_id=generate_run_id("locomo"),
        suite="locomo",
        status=RunStatus.RUNNING,
        started_at=now_iso(),
        systems=SYSTEMS,
        config=config.model_dump(mode="json"),
        export_metadata={
            "format": "mneno-bench.locomo",
            "version": 1,
            "suite_name": SUITE_NAME,
            "evaluation_mode": config.mode,
            "execution": _execution_metadata(config.workers, 1, "serial"),
        },
    )


def _finish_missing_dataset(
    run: BenchmarkRun, result_path: Path, report_path: Path, reason: str
) -> BenchmarkRun:
    run.status = RunStatus.DATASET_MISSING
    run.finished_at = now_iso()
    run.errors = []
    run.export_metadata["locomo"] = {
        "dataset_status": RunStatus.DATASET_MISSING.value,
        "execution_status": RunStatus.SKIPPED.value,
        "evaluation_mode": run.config.get("mode", "retrieval_only"),
        "execution_phase": run.config.get("phase", "full"),
        "execution": run.export_metadata["execution"],
        "skip_reason": reason,
        "dataset": {
            "source_path": None,
            "conversation_count": 0,
            "message_count": 0,
            "question_count": 0,
            "categories": {},
        },
        "systems": {
            system: {
                "status": RunStatus.SKIPPED.value,
                "metrics": {},
                "score_labels": _empty_score_labels(),
                "trace_ids": [],
                "judge": {"status": "skipped", "reason": "Dataset missing."},
                "skip_reason": "LOCOMO dataset is not installed.",
            }
            for system in SYSTEMS
        },
        "official_scoring": {
            "status": "unavailable",
            "reason": "Dataset missing.",
        },
        "result_path": str(result_path),
        "report_path": str(report_path),
        "trace_directory": str(result_path.parent / "traces"),
        "raw_output_directory": str(result_path.parent / "raw"),
        "judge_prompt_directory": str(result_path.parent / "judge" / "prompts"),
        "judge_response_directory": str(result_path.parent / "judge" / "responses"),
    }
    _write_failure_analysis(run, result_path.parents[1])
    _write_dashboard_run(run, result_path.parents[1])
    save_json(result_path, run.model_dump(mode="json"))
    _write_report(run, report_path)
    console.print("[yellow]LOCOMO dataset missing; wrote a skipped report.[/yellow]")
    return run


def _conversation_jobs(
    dataset: LOCOMODataset, max_cases: int | None
) -> list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]]:
    jobs: list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]] = []
    remaining = max_cases
    for index, conversation in enumerate(dataset.conversations):
        if remaining is not None and remaining <= 0:
            break
        questions = conversation.questions
        if remaining is not None:
            questions = questions[:remaining]
            remaining -= len(questions)
        if questions:
            jobs.append((index, conversation, questions))
    return jobs


def _filter_resumed_jobs(
    jobs: list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]],
    resumed_case_ids: set[str],
) -> list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]]:
    if not resumed_case_ids:
        return jobs
    filtered: list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]] = []
    for index, conversation, questions in jobs:
        remaining = [question for question in questions if question.id not in resumed_case_ids]
        if remaining:
            filtered.append((index, conversation, remaining))
    return filtered


def _execution_metadata(
    requested_workers: int,
    effective_workers: int,
    backend: str,
    resumed_cases: int = 0,
) -> dict[str, Any]:
    latency_comparable = effective_workers == 1
    return {
        "requested_workers": requested_workers,
        "effective_workers": effective_workers,
        "backend": backend,
        "result_order": "dataset",
        "latency_comparable": latency_comparable,
        "latency_note": (
            "Per-case latency is suitable for serial comparison."
            if latency_comparable
            else "Parallel resource contention makes per-case latency unsuitable "
            "for comparison with serial runs."
        ),
        "resumed_cases": resumed_cases,
    }


def _execute_conversation_jobs(
    *,
    jobs: list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]],
    sdk: MnenoAdapter,
    mneno_available: bool,
    results_dir: Path,
    run_id: str,
    k: int,
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
    backend: str,
    workers: int,
    total_cases: int,
    progress_started_at: float,
    initial_completed: int = 0,
    checkpoint_dir: Path | None = None,
    checkpoint_fingerprint: str | None = None,
) -> list[_ConversationOutcome]:
    if not jobs:
        return []
    outcomes: list[_ConversationOutcome] = []
    progress = _CaseProgress(total_cases, progress_started_at, initial_completed)

    if backend == "serial":
        for index, conversation, questions in jobs:
            outcome = _execute_conversation(
                index,
                conversation,
                questions,
                sdk,
                mneno_available,
                results_dir,
                run_id,
                k,
                config,
                judge,
                progress.advance,
                checkpoint_dir=checkpoint_dir,
                checkpoint_fingerprint=checkpoint_fingerprint,
            )
            outcomes.append(outcome)
        return outcomes

    executor_type = ProcessPoolExecutor if backend == "process" else ThreadPoolExecutor
    if backend == "process":
        with multiprocessing.Manager() as manager:
            progress_queue = manager.Queue()
            with executor_type(max_workers=workers) as executor:
                futures = [
                    executor.submit(
                        _execute_conversation_process,
                        index,
                        conversation,
                        questions,
                        results_dir,
                        run_id,
                        k,
                        config,
                        progress_queue,
                        checkpoint_dir,
                        checkpoint_fingerprint,
                    )
                    for index, conversation, questions in jobs
                ]
                pending = set(futures)
                while pending:
                    done, pending = wait(
                        pending, timeout=0.25, return_when=FIRST_COMPLETED
                    )
                    _drain_progress_queue(progress_queue, progress)
                    for future in done:
                        outcomes.append(future.result())
                _drain_progress_queue(progress_queue, progress)
        return outcomes

    with executor_type(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _execute_conversation,
                index,
                conversation,
                questions,
                sdk,
                mneno_available,
                results_dir,
                run_id,
                k,
                config,
                judge,
                progress.advance,
                checkpoint_dir=checkpoint_dir,
                checkpoint_fingerprint=checkpoint_fingerprint,
            )
            for index, conversation, questions in jobs
        ]
        pending = set(futures)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                outcomes.append(future.result())
    return outcomes


def _drain_progress_queue(progress_queue: Any, progress: _CaseProgress) -> None:
    while True:
        try:
            progress.advance(int(progress_queue.get_nowait()))
        except Empty:
            return


def _execute_conversation_process(
    index: int,
    conversation: LOCOMOConversation,
    questions: list[LOCOMOQuestion],
    results_dir: Path,
    run_id: str,
    k: int,
    config: LOCOMOEvaluationConfig,
    progress_queue: Any,
    checkpoint_dir: Path | None = None,
    checkpoint_fingerprint: str | None = None,
) -> _ConversationOutcome:
    sdk = MnenoAdapter()
    mneno_available = sdk.is_available()
    judge = _build_judge(config, results_dir, run_id)
    return _execute_conversation(
        index,
        conversation,
        questions,
        sdk,
        mneno_available,
        results_dir,
        run_id,
        k,
        config,
        judge,
        lambda: progress_queue.put(1),
        checkpoint_dir=checkpoint_dir,
        checkpoint_fingerprint=checkpoint_fingerprint,
    )


def _execute_conversation(
    index: int,
    conversation: LOCOMOConversation,
    questions: list[LOCOMOQuestion],
    sdk: MnenoAdapter,
    mneno_available: bool,
    results_dir: Path,
    run_id: str,
    k: int,
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
    progress_callback: Callable[[], None] | None = None,
    checkpoint_dir: Path | None = None,
    checkpoint_fingerprint: str | None = None,
) -> _ConversationOutcome:
    metrics_by_system: dict[str, list[dict[str, float | int | None]]] = defaultdict(
        list
    )
    judge_status_by_system: dict[str, list[str]] = defaultdict(list)
    trace_ids_by_system: dict[str, list[str]] = defaultdict(list)
    system_errors: dict[str, list[str]] = defaultdict(list)
    results: list[BenchmarkResult] = []
    memories = [
        message.as_benchmark_memory(conversation.id)
        for message in conversation.messages
    ]
    runtime = (
        _initialize_mneno_conversation(sdk, conversation, memories, config)
        if mneno_available
        else None
    )
    checkpoint_store = (
        LOCOMOCaseCheckpointStore(checkpoint_dir, checkpoint_fingerprint)
        if checkpoint_dir is not None and checkpoint_fingerprint is not None
        else None
    )

    for question_index, question in enumerate(questions):
        baseline_results: list[BaselineResult] = []
        case_metrics: dict[str, list[MetricResult]] = {}
        for system, baseline in (
            ("keyword_baseline", keyword_baseline),
            ("full_context_baseline", full_context_baseline),
        ):
            raw = baseline(memories, question.question, k=k)
            retrieved_ids = _search_ids(raw)
            values = _retrieval_metrics(retrieved_ids, question)
            answer = _answer_for_mode(
                config,
                system,
                question,
                _context_text(memories, retrieved_ids),
            )
            judge_result = _judge_for_mode(
                config,
                judge,
                question,
                answer,
                results_dir,
                run_id,
                system,
            )
            _apply_answer_metrics(values, question, answer, judge_result, config)
            if judge_result is not None:
                judge_status_by_system[system].append(judge_result.status)
            metrics_by_system[system].append(values)
            normalized = _normalized_result(
                system,
                question,
                values,
                retrieved_ids=retrieved_ids,
                answer=answer,
                judge_result=judge_result,
            )
            baseline_results.append(
                BaselineResult(
                    name=system,
                    retrieved_memory_ids=retrieved_ids,
                    context_tokens=_context_tokens(memories, retrieved_ids),
                    latency_ms=float(raw.metrics.get("latency_ms") or 0.0),
                    metadata={
                        "conversation_id": conversation.id,
                        "category": question.category,
                        "normalized_result": raw.model_dump(mode="json"),
                        "locomo_result": normalized.model_dump(mode="json"),
                        "answer_candidate": (
                            answer.model_dump(mode="json") if answer else None
                        ),
                        "judge_result": (
                            judge_result.model_dump(mode="json")
                            if judge_result
                            else None
                        ),
                    },
                )
            )
            case_metrics[system] = _metric_results(values)

        if not mneno_available:
            mneno_result = MnenoResult(
                status=RunStatus.SKIPPED,
                skip_reason=INSTALL_MESSAGE,
                metadata={"conversation_id": conversation.id},
            )
            case_metrics["mneno"] = official_metric_placeholders()
        elif runtime is None:
            reason = "Mneno conversation initialization failed."
            mneno_result = MnenoResult(
                status=RunStatus.FAILED,
                error=reason,
                metadata={"conversation_id": conversation.id},
            )
            system_errors["mneno"].append(reason)
            case_metrics["mneno"] = official_metric_placeholders()
        else:
            mneno_result, values, normalized = _execute_mneno_question(
                sdk,
                runtime,
                conversation,
                question,
                memories,
                results_dir,
                run_id,
                k,
                config,
                judge,
            )
            case_metrics["mneno"] = _metric_results(values)
            mneno_result.metadata["locomo_result"] = normalized.model_dump(mode="json")
            if mneno_result.status == RunStatus.COMPLETED:
                metrics_by_system["mneno"].append(values)
                trace_ids_by_system["mneno"].extend(normalized.trace_ids)
                judge_result = normalized.metadata.get("judge_result")
                if isinstance(judge_result, dict):
                    judge_status_by_system["mneno"].append(
                        str(judge_result.get("status", "unknown"))
                    )
            elif mneno_result.error:
                system_errors["mneno"].append(mneno_result.error)

        result = BenchmarkResult(
            case=_benchmark_case(question),
            baseline_results=baseline_results,
            mneno_result=mneno_result,
            metrics=case_metrics,
        )
        results.append(result)
        if checkpoint_store is not None:
            checkpoint_store.save_case(
                _case_dataset_index(conversation.id, question_index, question), result
            )
        if progress_callback is not None:
            progress_callback()

    return _ConversationOutcome(
        index=index,
        results=results,
        metrics_by_system=dict(metrics_by_system),
        judge_status_by_system=dict(judge_status_by_system),
        trace_ids_by_system=dict(trace_ids_by_system),
        system_errors=dict(system_errors),
        reranker_stats=_reranker_stats(runtime),
    )


def _extend_grouped(
    target: dict[str, list[Any]], source: Mapping[str, list[Any]]
) -> None:
    for key, values in source.items():
        target[key].extend(values)


def _initialize_mneno_conversation(
    sdk: MnenoAdapter,
    conversation: LOCOMOConversation,
    memories: list[dict[str, Any]],
    config: LOCOMOEvaluationConfig,
) -> dict[str, Any] | None:
    try:
        reranker = _build_mneno_reranker(config)
        client_kwargs: dict[str, Any] = {"trace_enabled": True}
        if reranker is not None:
            client_kwargs["reranker_provider"] = reranker
        client = sdk.create_client(**client_kwargs)
        id_map: dict[str, str] = {}
        session_id_map: dict[str, str] = {}
        if sdk.supports("create_session", client=client):
            for session_id in sorted(
                {
                    str(memory["session_id"])
                    for memory in memories
                    if memory.get("session_id")
                }
            ):
                try:
                    session = sdk.create_session(
                        client=client,
                        session_id=session_id,
                        id=session_id,
                        title=f"LOCOMO session {session_id}",
                        metadata={
                            "benchmark": "locomo",
                            "conversation_id": conversation.id,
                        },
                    )
                    internal_id = _value(session, "session_id") or _value(session, "id")
                    session_id_map[session_id] = str(internal_id or session_id)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    break
        for memory in memories:
            payload = dict(memory)
            dataset_id = str(payload["id"])
            raw_session_id = payload.get("session_id")
            if raw_session_id is not None:
                payload["session_id"] = session_id_map.get(
                    str(raw_session_id), str(raw_session_id)
                )
            if sdk.supports("add_with_report", client=client):
                report = sdk.add_with_report(client, payload)
                internal_id = _internal_memory_id(report)
                id_map[dataset_id] = str(internal_id or dataset_id)
            else:
                raw = sdk.add_memory(client, payload)
                internal_id = _internal_memory_id(raw)
                id_map[dataset_id] = str(internal_id or dataset_id)
        return {
            "client": client,
            "id_map": id_map,
            "reverse_id_map": {value: key for key, value in id_map.items()},
            "session_id_map": session_id_map,
            "conversation_id": conversation.id,
            "reranker_provider": reranker,
        }
    except Exception:
        return None


def _build_mneno_reranker(
    config: LOCOMOEvaluationConfig,
) -> CachedRerankerProvider | None:
    if not config.mneno_reranker_model:
        return None
    client = LLMClient(
        LLMConfig(
            model=config.mneno_reranker_model,
            provider=config.mneno_reranker_provider,
            api_base=config.mneno_reranker_api_base,
            api_key_required=config.mneno_reranker_api_key_required,
            requests_per_minute=config.external_requests_per_minute,
            max_concurrent_requests=config.external_max_concurrent_requests,
            max_retries=config.mneno_reranker_retries,
            retry_backoff_seconds=config.external_retry_backoff_seconds,
            retry_backoff_max_seconds=config.external_retry_backoff_max_seconds,
            retry_jitter_seconds=config.external_retry_jitter_seconds,
            extra={
                "timeout": config.mneno_reranker_timeout_seconds,
                "num_retries": 0,
            },
        ),
        allow_external_calls=config.allow_external_calls,
    )
    return CachedRerankerProvider(
        client,
        candidate_limit=config.mneno_reranker_candidate_limit,
        cache_size=config.mneno_reranker_cache_size,
    )


def _reranker_metadata(runtime: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if runtime is None:
        return None
    provider = runtime.get("reranker_provider")
    metadata = getattr(provider, "metadata", None)
    if not callable(metadata):
        return None
    value = metadata()
    return dict(value) if isinstance(value, Mapping) else None


def _reranker_stats(runtime: Mapping[str, Any] | None) -> dict[str, int]:
    metadata = _reranker_metadata(runtime) or {}
    return {
        key: int(metadata.get(key, 0))
        for key in (
            "api_requests",
            "cache_hits",
            "cache_misses",
            "documents_sent",
        )
    }


def _reranker_run_metadata(
    config: LOCOMOEvaluationConfig, stats: Mapping[str, int]
) -> dict[str, Any]:
    return {
        "enabled": bool(config.mneno_reranker_model),
        "model": config.mneno_reranker_model,
        "provider": config.mneno_reranker_provider,
        "api_base_configured": bool(config.mneno_reranker_api_base),
        "candidate_limit": config.mneno_reranker_candidate_limit,
        "cache_size": config.mneno_reranker_cache_size,
        "timeout_seconds": config.mneno_reranker_timeout_seconds,
        "retries": config.mneno_reranker_retries,
        "stats": dict(stats),
        "rate_limit": {
            "requests_per_minute": config.external_requests_per_minute,
            "max_concurrent_requests": config.external_max_concurrent_requests,
            "external_retries": config.external_retries,
            "retry_backoff_seconds": config.external_retry_backoff_seconds,
            "retry_backoff_max_seconds": config.external_retry_backoff_max_seconds,
            "retry_jitter_seconds": config.external_retry_jitter_seconds,
        },
    }


def _execute_mneno_question(
    sdk: MnenoAdapter,
    runtime: dict[str, Any],
    conversation: LOCOMOConversation,
    question: LOCOMOQuestion,
    memories: list[dict[str, Any]],
    results_dir: Path,
    run_id: str,
    k: int,
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
) -> tuple[MnenoResult, dict[str, float | int | None], NormalizedLOCOMOResult]:
    client = runtime["client"]
    reverse_id_map = runtime["reverse_id_map"]
    if not sdk.supports("evaluate_search", client=client):
        result = MnenoResult(
            status=RunStatus.SKIPPED,
            skip_reason="Installed Mneno does not expose evaluate_search().",
            metadata={"conversation_id": conversation.id},
        )
        values = _retrieval_metrics([], question)
        return result, values, _normalized_result("mneno", question, values)

    try:
        search = sdk.evaluate_search(
            client=client,
            query=question.question,
            expected_memory_ids=question.evidence_ids,
            k=k,
            limit=k,
        )
        context: NormalizedContextResult | None = None
        if sdk.supports("evaluate_context", client=client):
            context = sdk.evaluate_context(
                client=client,
                query=question.question,
                expected_memory_ids=question.evidence_ids,
                expected_answer=question.expected_answers,
            )
        built_context: Any = None
        if sdk.supports("build_context", client=client):
            built_context = sdk.build_context(
                client=client,
                query=question.question,
                expected_memory_ids=question.evidence_ids,
                forbidden_memory_ids=[],
                limit=k,
            )

        retrieved_ids = _normalize_ids(_search_ids(search), reverse_id_map)
        included_ids = _normalize_ids(
            _context_ids(built_context, "included"), reverse_id_map
        )
        excluded_ids = _normalize_ids(
            _context_ids(built_context, "excluded"), reverse_id_map
        )
        metric_ids = included_ids or retrieved_ids
        trace_ids = _unique_strings(
            [
                search.trace_id,
                context.trace_id if context is not None else None,
                _value(built_context, "trace_id"),
            ]
        )
        trace_summary, trace_locations = _export_traces(
            sdk,
            client,
            trace_ids,
            results_dir,
            run_id,
            question.id,
        )
        values = _retrieval_metrics(metric_ids, question)
        answer = _answer_for_mode(
            config,
            "mneno",
            question,
            _context_text(memories, metric_ids),
            trace_ids=trace_ids,
            metadata={"context_source": "mneno_built_context_or_search"},
        )
        judge_result = _judge_for_mode(
            config,
            judge,
            question,
            answer,
            results_dir,
            run_id,
            "mneno",
        )
        _apply_answer_metrics(values, question, answer, judge_result, config)
        raw_output = {
            "search": search.model_dump(mode="json"),
            "context": context.model_dump(mode="json") if context else None,
            "built_context": built_context,
            "retrieved_dialog_ids": retrieved_ids,
            "included_dialog_ids": included_ids,
            "excluded_dialog_ids": excluded_ids,
            "trace_locations": trace_locations,
            "answer_candidate": answer.model_dump(mode="json") if answer else None,
            "judge_result": judge_result.model_dump(mode="json")
            if judge_result
            else None,
            "reranker": _reranker_metadata(runtime),
        }
        raw_path = (
            results_dir / "locomo" / "raw" / run_id / f"{_safe_name(question.id)}.json"
        )
        save_json(raw_path, raw_output)
        normalized = _normalized_result(
            "mneno",
            question,
            values,
            retrieved_ids=metric_ids,
            trace_ids=trace_ids,
            answer=answer,
            judge_result=judge_result,
            metadata={"raw_output_path": str(raw_path)},
        )
        return (
            MnenoResult(
                status=RunStatus.COMPLETED,
                retrieved_memory_ids=retrieved_ids,
                included_memory_ids=included_ids,
                excluded_memory_ids=excluded_ids,
                context_tokens=_context_tokens(memories, metric_ids),
                latency_ms=float(search.metrics.get("latency_ms") or 0.0),
                trace_summary=trace_summary,
                trace_ids=trace_ids,
                metadata={
                    "conversation_id": conversation.id,
                    "raw_output_path": str(raw_path),
                    "trace_locations": trace_locations,
                    "answer_candidate": answer.model_dump(mode="json")
                    if answer
                    else None,
                    "judge_result": judge_result.model_dump(mode="json")
                    if judge_result
                    else None,
                    "reranker": _reranker_metadata(runtime),
                },
            ),
            values,
            normalized,
        )
    except Exception as exc:
        values = _retrieval_metrics([], question)
        normalized = _normalized_result(
            "mneno", question, values, metadata={"error": str(exc)}
        )
        return (
            MnenoResult(
                status=RunStatus.FAILED,
                error=str(exc),
                metadata={
                    "conversation_id": conversation.id,
                    "reranker": _reranker_metadata(runtime),
                },
            ),
            values,
            normalized,
        )


def _export_traces(
    sdk: MnenoAdapter,
    client: Any,
    trace_ids: list[str],
    results_dir: Path,
    run_id: str,
    question_id: str,
) -> tuple[TraceSummary | None, list[str]]:
    if not trace_ids or not sdk.supports("export_trace", client=client):
        return None, []
    summaries: list[TraceSummary] = []
    locations: list[str] = []
    for trace_id in trace_ids:
        try:
            raw_trace = sdk.export_trace(client=client, trace_id=trace_id)
            path = (
                results_dir
                / "locomo"
                / "traces"
                / f"{run_id}-{_safe_name(question_id)}-{_safe_name(trace_id)}.json.gz"
            )
            save_json(path, raw_trace)
            locations.append(str(path))
            summary = TraceLoader().load_trace(raw_trace)
            summary.raw_trace_reference = str(path)
            summaries.append(summary)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
    return (_merge_trace_summaries(summaries) if summaries else None), locations


def _merge_trace_summaries(summaries: list[TraceSummary]) -> TraceSummary:
    return TraceSummary(
        trace_id=summaries[0].trace_id,
        operation_count=sum(item.operation_count for item in summaries),
        event_count=sum(item.event_count for item in summaries),
        decision_count=sum(item.decision_count for item in summaries),
        duration_ms=(
            round(
                sum(item.duration_ms or 0.0 for item in summaries),
                4,
            )
            if any(item.duration_ms is not None for item in summaries)
            else None
        ),
        retrieved_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.retrieved_memory_ids
        ),
        selected_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.selected_memory_ids
        ),
        included_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.included_memory_ids
        ),
        excluded_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.excluded_memory_ids
        ),
        suppressed_memory_ids=_unique_strings(
            item for summary in summaries for item in summary.suppressed_memory_ids
        ),
        conflict_resolutions=_unique_strings(
            item for summary in summaries for item in summary.conflict_resolutions
        ),
        lifecycle_events=_unique_strings(
            item for summary in summaries for item in summary.lifecycle_events
        ),
        explanations=_unique_strings(
            item for summary in summaries for item in summary.explanations
        ),
        raw_trace_reference=";".join(
            item.raw_trace_reference for item in summaries if item.raw_trace_reference
        )
        or None,
    )


def _build_summary(
    dataset: LOCOMODataset,
    metrics_by_system: Mapping[str, list[dict[str, float | int | None]]],
    trace_ids_by_system: Mapping[str, list[str]],
    judge_status_by_system: Mapping[str, list[str]],
    system_errors: Mapping[str, list[str]],
    mneno_available: bool,
    config: LOCOMOEvaluationConfig,
    validation_warnings: list[dict[str, object]],
    result_path: Path,
    report_path: Path,
    run: BenchmarkRun,
) -> dict[str, Any]:
    categories = Counter(
        _category_name(question.category)
        for conversation in dataset.conversations
        for question in conversation.questions
    )
    systems: dict[str, Any] = {}
    for system in SYSTEMS:
        errors = system_errors.get(system, [])
        if system == "mneno" and not mneno_available:
            status = RunStatus.SKIPPED
            skip_reason = INSTALL_MESSAGE
        elif errors:
            status = RunStatus.FAILED
            skip_reason = None
        else:
            status = RunStatus.COMPLETED
            skip_reason = None
        systems[system] = {
            "status": status.value,
            "metrics": aggregate_metric_maps(metrics_by_system.get(system, [])),
            "score_labels": _score_labels(
                aggregate_metric_maps(metrics_by_system.get(system, []))
            ),
            "trace_ids": _unique_strings(trace_ids_by_system.get(system, [])),
            "judge": _judge_summary(config, judge_status_by_system.get(system, [])),
            "skip_reason": skip_reason,
            "errors": list(errors),
        }
    return {
        "dataset_status": "available",
        "execution_status": RunStatus.COMPLETED.value,
        "evaluation_mode": config.mode,
        "execution_phase": config.phase,
        "execution": run.export_metadata["execution"],
        "dataset_validation": {
            "strict": config.strict_dataset_validation,
            "allow_malformed_evidence": config.allow_malformed_evidence,
            "malformed_evidence_warning_count": len(validation_warnings),
            "warnings": validation_warnings,
        },
        "dataset": {
            "source_path": dataset.source_path,
            "benchmark_version": dataset.benchmark_version,
            "conversation_count": len(dataset.conversations),
            "message_count": dataset.message_count,
            "question_count": dataset.question_count,
            "categories": dict(sorted(categories.items())),
        },
        "systems": systems,
        "official_scoring": {
            "status": "unavailable",
            "reason": (
                "Official LOCOMO QA F1/category scoring is computed on local "
                "diagnostic answer candidates as locomo_official_f1_on_candidate; "
                "official_score remains null because generation is diagnostic."
                if config.mode == "deterministic_answer"
                else OFFICIAL_SCORING_PENDING
            ),
        },
        "judge_model": config.judge_model,
        "judge_provider": config.judge_provider,
        "prompt_version": config.prompt_version,
        "mneno_version": run.mneno_version,
        "mneno_reranker": run.export_metadata.get("mneno_reranker"),
        "external_requests": run.export_metadata.get("external_requests", {}),
        "checkpointing": run.export_metadata.get("checkpointing", {}),
        "result_path": str(result_path),
        "report_path": str(report_path),
        "trace_directory": str(result_path.parent / "traces"),
        "raw_output_directory": str(result_path.parent / "raw"),
        "judge_prompt_directory": str(result_path.parent / "judge" / "prompts"),
        "judge_response_directory": str(result_path.parent / "judge" / "responses"),
    }


def _benchmark_case(question: LOCOMOQuestion) -> BenchmarkCase:
    return BenchmarkCase(
        id=question.id,
        query=question.question,
        expected_memory_ids=question.evidence_ids,
        tags=[_category_name(question.category)],
        metadata={
            "benchmark": "locomo",
            "conversation_id": question.conversation_id,
            "category": question.category,
            "category_name": _category_name(question.category),
            "expected_answers": question.expected_answers,
            "official_scoring": "official_locomo_qa_f1_available_when_answer_exists",
            **question.metadata,
        },
    )


def _retrieval_metrics(
    retrieved_ids: list[str], question: LOCOMOQuestion
) -> dict[str, float | int | None]:
    return {
        "evidence_recall": evidence_recall(retrieved_ids, question.evidence_ids),
        "evidence_precision": evidence_precision(retrieved_ids, question.evidence_ids),
        "retrieval_hit_rate": retrieval_hit_rate(retrieved_ids, question.evidence_ids),
        "retrieved_dialog_count": len(retrieved_ids),
        "official_score": None,
        "diagnostic_score": None,
        "retrieval_diagnostic": evidence_recall(retrieved_ids, question.evidence_ids),
        "judge_score": None,
        "factual_recall": None,
        "temporal_reasoning": None,
        "multi_hop_reasoning": None,
        "multi_session_reasoning": None,
    }


def _metric_results(values: Mapping[str, float | int | None]) -> list[MetricResult]:
    placeholders = {metric.name: metric for metric in official_metric_placeholders()}
    results: list[MetricResult] = []
    for name, value in sorted(values.items()):
        if name in placeholders:
            results.append(placeholders[name].model_copy(update={"value": value}))
        else:
            results.append(
                MetricResult(
                    name=name,
                    value=float(value) if value is not None else None,
                    unit="count" if name.endswith("_count") else "ratio",
                    description=(
                        "Official evidence dialog IDs retrieved divided by "
                        "available official evidence IDs."
                        if name == "evidence_recall"
                        else _metric_description(name)
                    ),
                    unavailable_reason=(
                        "This question has no official evidence IDs."
                        if name == "evidence_recall" and value is None
                        else None
                    ),
                )
            )
    return results


def _normalized_result(
    provider: str,
    question: LOCOMOQuestion,
    metrics: dict[str, float | int | None],
    retrieved_ids: list[str] | None = None,
    trace_ids: list[str] | None = None,
    answer: AnswerCandidate | None = None,
    judge_result: JudgeResult | None = None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedLOCOMOResult:
    return NormalizedLOCOMOResult(
        provider=provider,
        metrics=metrics,
        official_score=_float_or_none(metrics.get("official_score")),
        diagnostic_score=_float_or_none(metrics.get("diagnostic_score")),
        retrieval_diagnostic=_float_or_none(metrics.get("retrieval_diagnostic")),
        judge_score=_float_or_none(metrics.get("judge_score")),
        trace_ids=trace_ids or [],
        metadata={
            "question_id": question.id,
            "conversation_id": question.conversation_id,
            "category": question.category,
            "expected_answers": question.expected_answers,
            "evidence_ids": question.evidence_ids,
            "retrieved_dialog_ids": retrieved_ids or [],
            "official_scoring": "separate_score_label",
            "answer_candidate": answer.model_dump(mode="json") if answer else None,
            "judge_result": judge_result.model_dump(mode="json")
            if judge_result
            else None,
            **(metadata or {}),
        },
    )


def _write_report(run: BenchmarkRun, path: Path) -> None:
    summary = run.export_metadata["locomo"]
    dataset = summary["dataset"]
    judge_requested = summary.get("evaluation_mode") == "llm_judge"
    judge_model = summary.get("judge_model") if judge_requested else "not requested"
    judge_provider = (
        summary.get("judge_provider") if judge_requested else "not requested"
    )
    reranker = summary.get("mneno_reranker") or {}
    external_requests = summary.get("external_requests") or {}
    checkpointing = summary.get("checkpointing") or {}
    lines = [
        "# LOCOMO External Benchmark",
        "",
        f"- Run ID: `{run.run_id}`",
        f"- Status: **{run.status.value}**",
        f"- Dataset status: **{summary['dataset_status']}**",
        f"- Evaluation mode: **{summary.get('evaluation_mode', 'retrieval_only')}**",
        f"- Execution phase: **{summary.get('execution_phase', 'full')}**",
        f"- Workers: **{summary.get('execution', {}).get('effective_workers', 1)}**",
        f"- Parallel backend: **{summary.get('execution', {}).get('backend', 'serial')}**",
        "- Latency comparable with serial runs: "
        f"**{'yes' if summary.get('execution', {}).get('latency_comparable', True) else 'no'}**",
        f"- Benchmark version: **{run.benchmark_version}**",
        f"- LOCOMO dataset version: **{dataset.get('benchmark_version', 'unavailable')}**",
        f"- Mneno version: **{run.mneno_version or 'not installed'}**",
        f"- Mneno reranker: **{reranker.get('model') or 'disabled'}**",
        f"- Resumed cases: **{checkpointing.get('resumed_cases', 0)}**",
        f"- Conversations: **{dataset['conversation_count']}**",
        f"- Messages: **{dataset['message_count']}**",
        f"- Questions: **{dataset['question_count']}**",
        "",
    ]
    if run.status == RunStatus.DATASET_MISSING:
        lines.extend(
            [
                "## Skipped",
                "",
                summary["skip_reason"],
                "",
                "Place the official dataset at `data/locomo/raw/locomo10.json`.",
            ]
        )
    else:
        lines.extend(
            [
                "## Execution Status",
                "",
                "| System | Status | Official Score | Diagnostic Score | Evidence Recall | Judge Score |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for system in SYSTEMS:
            item = summary["systems"][system]
            lines.append(
                f"| {system} | {item['status']} | "
                f"{_format_score(item['metrics'].get('official_score'))} | "
                f"{_format_score(item['metrics'].get('diagnostic_score'))} | "
                f"{_format_score(item['metrics'].get('evidence_recall'))} | "
                f"{_format_score(item['metrics'].get('judge_score'))} |"
            )
        lines.extend(
            [
                "",
                "## LOCOMO Metrics",
                "",
                "Retrieval diagnostics are always separated from answer quality. "
                "Deterministic answer candidates are local diagnostics. The "
                "official-compatible QA score reproduces the released LOCOMO "
                "category/F1 evaluator but must not be compared with leaderboard "
                "model scores unless the answer-generation setup also matches.",
                "",
                "Evidence recall is a retrieval diagnostic over official dialog "
                "evidence IDs; it is not an official LOCOMO answer score.",
                "",
                "## Mneno Reranker",
                "",
                f"- Enabled: **{'yes' if reranker.get('enabled') else 'no'}**",
                f"- Provider: **{reranker.get('provider') or 'not configured'}**",
                f"- Candidate limit: **{reranker.get('candidate_limit', 0)}**",
                f"- API requests: **{reranker.get('stats', {}).get('api_requests', 0)}**",
                f"- Cache hits: **{reranker.get('stats', {}).get('cache_hits', 0)}**",
                f"- Documents sent: **{reranker.get('stats', {}).get('documents_sent', 0)}**",
                "",
                "## External Request Controls",
                "",
                f"- Successful requests: **{external_requests.get('successful_requests', 0)}**",
                f"- Attempts: **{external_requests.get('attempts', 0)}**",
                f"- Retries: **{external_requests.get('retries', 0)}**",
                f"- HTTP 429s: **{external_requests.get('rate_limited_429s', 0)}**",
                f"- Failures: **{external_requests.get('failures', 0)}**",
                "",
                "## Judge",
                "",
                f"- Model: **{judge_model or 'not configured'}**",
                f"- Provider: **{judge_provider or 'not configured'}**",
                f"- Prompt version: **{summary.get('prompt_version')}**",
                f"- Prompts: `{summary['judge_prompt_directory']}`",
                f"- Responses: `{summary['judge_response_directory']}`",
                "",
                "## Dataset Validation",
                "",
                f"- Strict: **{summary['dataset_validation']['strict']}**",
                f"- Malformed evidence warnings: **{summary['dataset_validation']['malformed_evidence_warning_count']}**",
                "",
                "## Raw Outputs",
                "",
                f"- Mneno traces: `{summary['trace_directory']}`",
                f"- Mneno normalized/raw outputs: `{summary['raw_output_directory']}`",
            ]
        )
    failure_analysis = summary.get("failure_analysis", {})
    lines.extend(
        [
            "",
            "## Failure Analysis",
            "",
            f"- Failure count: **{failure_analysis.get('failure_count', 0)}**",
            "- Top categories overall: "
            + _format_counts(failure_analysis.get("top_categories_overall", {})),
            "- Top categories for Mneno: "
            + _format_counts(failure_analysis.get("top_categories_mneno", {})),
            "- Top categories for baselines: "
            + _format_counts(failure_analysis.get("top_categories_baselines", {})),
            "- Suggested Mneno Core actions: "
            + (
                "; ".join(failure_analysis.get("mneno_suggested_actions", [])) or "none"
            ),
            "- Baseline interpretation: failures remain visible as comparison evidence; Full Context stale-memory inclusion and Keyword lexical or session limitations may be expected baseline behavior.",
            "- Worst cases: "
            + _format_worst_cases(failure_analysis.get("worst_cases", [])),
        ]
    )
    if failure_analysis:
        lines.extend(
            [
                f"- Failure JSON: `{failure_analysis['json_path']}`",
                f"- Failure report: `{failure_analysis['report_path']}`",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _checkpoint_store(
    dataset: LOCOMODataset,
    config: LOCOMOEvaluationConfig,
    results_dir: Path,
    run: BenchmarkRun,
    k: int,
) -> LOCOMOCaseCheckpointStore:
    fingerprint = _checkpoint_fingerprint(dataset, config, run, k)
    evaluation_fingerprint = _evaluation_checkpoint_fingerprint(config)
    directory = (
        Path(config.checkpoint_dir)
        if config.checkpoint_dir
        else results_dir / "locomo" / "checkpoints" / fingerprint[:16]
    )
    return LOCOMOCaseCheckpointStore(directory, fingerprint, evaluation_fingerprint)


def _checkpoint_fingerprint(
    dataset: LOCOMODataset,
    config: LOCOMOEvaluationConfig,
    run: BenchmarkRun,
    k: int,
) -> str:
    comparable_config = config.model_dump(
        mode="json",
        exclude={
            "resume",
            "reuse_failed_checkpoints",
            "checkpoint_dir",
            "output_dir",
            "phase",
            "judge_model",
            "judge_provider",
            "judge_config_path",
            "save_judge_prompts",
            "prompt_version",
            "external_requests_per_minute",
            "external_max_concurrent_requests",
            "external_retries",
            "external_retry_backoff_seconds",
            "external_retry_backoff_max_seconds",
            "external_retry_jitter_seconds",
        },
    )
    return locomo_checkpoint_fingerprint(
        {
            "suite": "locomo",
            "benchmark_version": BENCHMARK_VERSION,
            "dataset": _dataset_identity(dataset),
            "k": k,
            "config": comparable_config,
            "mneno_version": run.mneno_version,
            "reranker": {
                "model": config.mneno_reranker_model,
                "provider": config.mneno_reranker_provider,
                "api_base": config.mneno_reranker_api_base,
                "candidate_limit": config.mneno_reranker_candidate_limit,
            },
        }
    )


def _evaluation_checkpoint_fingerprint(config: LOCOMOEvaluationConfig) -> str:
    return locomo_checkpoint_fingerprint(
        {
            "mode": config.mode,
            "judge_model": config.judge_model,
            "judge_provider": config.judge_provider,
            "judge_config_path": config.judge_config_path,
            "prompt_version": config.prompt_version,
        }
    )


def _dataset_identity(dataset: LOCOMODataset) -> dict[str, Any]:
    source = Path(dataset.source_path)
    stat: dict[str, Any] = {}
    try:
        details = source.stat()
        stat = {"size": details.st_size, "mtime_ns": details.st_mtime_ns}
    except OSError:
        stat = {}
    return {
        "source_path": str(source),
        "benchmark_version": dataset.benchmark_version,
        "conversation_count": len(dataset.conversations),
        "message_count": dataset.message_count,
        "question_count": dataset.question_count,
        "conversation_ids": [conversation.id for conversation in dataset.conversations],
        "question_ids": [
            question.id
            for conversation in dataset.conversations
            for question in conversation.questions
        ],
        "file": stat,
    }


def _checkpoint_manifest_metadata(
    dataset: LOCOMODataset,
    config: LOCOMOEvaluationConfig,
    run: BenchmarkRun,
    k: int,
    store: LOCOMOCaseCheckpointStore,
) -> dict[str, Any]:
    return {
        "suite": "locomo",
        "benchmark_version": BENCHMARK_VERSION,
        "dataset_identity": _dataset_identity(dataset),
        "config": config.model_dump(mode="json"),
        "k": k,
        "mneno_version": run.mneno_version,
        "prompt_version": config.prompt_version,
        "checkpoint_dir": str(store.directory),
        "retrieval_fingerprint": store.fingerprint,
        "evaluation_fingerprint": store.evaluation_fingerprint,
    }


def _uses_external_requests(config: LOCOMOEvaluationConfig) -> bool:
    return bool(config.mneno_reranker_model) or config.mode == "llm_judge"


def _stats_delta(
    before: Mapping[str, int | float], after: Mapping[str, int | float]
) -> dict[str, int | float]:
    keys = set(before) | set(after)
    return {
        key: round(float(after.get(key, 0)) - float(before.get(key, 0)), 4)
        for key in sorted(keys)
    }


def _collect_result_facts(
    results: list[BenchmarkResult],
) -> tuple[
    dict[str, list[dict[str, float | int | None]]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    metrics_by_system: dict[str, list[dict[str, float | int | None]]] = defaultdict(list)
    judge_status_by_system: dict[str, list[str]] = defaultdict(list)
    trace_ids_by_system: dict[str, list[str]] = defaultdict(list)
    system_errors: dict[str, list[str]] = defaultdict(list)
    for result in results:
        for system, metrics in result.metrics.items():
            metrics_by_system[system].append({metric.name: metric.value for metric in metrics})
        for baseline in result.baseline_results:
            judge_result = baseline.metadata.get("judge_result")
            if isinstance(judge_result, dict):
                judge_status_by_system[baseline.name].append(str(judge_result.get("status", "unknown")))
            if baseline.status == RunStatus.FAILED and baseline.error:
                system_errors[baseline.name].append(baseline.error)
        if result.mneno_result is not None:
            trace_ids_by_system["mneno"].extend(result.mneno_result.trace_ids)
            judge_result = result.mneno_result.metadata.get("judge_result")
            if isinstance(judge_result, dict):
                judge_status_by_system["mneno"].append(str(judge_result.get("status", "unknown")))
            if result.mneno_result.status == RunStatus.FAILED and result.mneno_result.error:
                system_errors["mneno"].append(result.mneno_result.error)
    return (
        dict(metrics_by_system),
        dict(judge_status_by_system),
        dict(trace_ids_by_system),
        dict(system_errors),
    )


def _case_dataset_index(
    conversation_id: str, question_index: int, question: LOCOMOQuestion
) -> int:
    del question_index
    match = re.search(r"qa-(\d+)$", question.id)
    question_number = int(match.group(1)) if match else 0
    conversation_hash = sum(ord(ch) for ch in conversation_id) % 10000
    return conversation_hash * 10000 + question_number


def _evaluate_resumed_predictions(
    jobs: list[tuple[int, LOCOMOConversation, list[LOCOMOQuestion]]],
    resumed_results: dict[str, BenchmarkResult],
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
    results_dir: Path,
    run_id: str,
    checkpoint_store: LOCOMOCaseCheckpointStore,
) -> dict[str, BenchmarkResult]:
    evaluated = dict(resumed_results)
    for _, conversation, questions in jobs:
        memories = [
            message.as_benchmark_memory(conversation.id)
            for message in conversation.messages
        ]
        for question_index, question in enumerate(questions):
            result = evaluated[question.id]
            updated = _evaluate_checkpoint_result(
                result,
                question,
                memories,
                config,
                judge,
                results_dir,
                run_id,
            )
            checkpoint_store.save_case(
                _case_dataset_index(conversation.id, question_index, question), updated
            )
            evaluated[question.id] = updated
    return evaluated


def _evaluate_checkpoint_result(
    result: BenchmarkResult,
    question: LOCOMOQuestion,
    memories: list[dict[str, Any]],
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
    results_dir: Path,
    run_id: str,
) -> BenchmarkResult:
    updated = result.model_copy(deep=True)
    for baseline in updated.baseline_results:
        values = _metric_value_map(updated.metrics.get(baseline.name, []))
        answer = _checkpoint_answer(
            baseline.metadata.get("answer_candidate"),
            config,
            baseline.name,
            question,
            memories,
            baseline.retrieved_memory_ids,
        )
        judge_result = _judge_for_mode(
            config,
            judge,
            question,
            answer,
            results_dir,
            run_id,
            baseline.name,
        )
        _apply_answer_metrics(values, question, answer, judge_result, config)
        baseline.metadata["answer_candidate"] = (
            answer.model_dump(mode="json") if answer else None
        )
        baseline.metadata["judge_result"] = (
            judge_result.model_dump(mode="json") if judge_result else None
        )
        baseline.metadata["locomo_result"] = _normalized_result(
            baseline.name,
            question,
            values,
            retrieved_ids=baseline.retrieved_memory_ids,
            answer=answer,
            judge_result=judge_result,
        ).model_dump(mode="json")
        updated.metrics[baseline.name] = _metric_results(values)

    if updated.mneno_result is not None:
        mneno = updated.mneno_result
        if mneno.status == RunStatus.COMPLETED:
            metric_ids = mneno.included_memory_ids or mneno.retrieved_memory_ids
            values = _metric_value_map(updated.metrics.get("mneno", []))
            answer = _checkpoint_answer(
                mneno.metadata.get("answer_candidate"),
                config,
                "mneno",
                question,
                memories,
                metric_ids,
                trace_ids=mneno.trace_ids,
            )
            judge_result = _judge_for_mode(
                config,
                judge,
                question,
                answer,
                results_dir,
                run_id,
                "mneno",
            )
            _apply_answer_metrics(values, question, answer, judge_result, config)
            mneno.metadata["answer_candidate"] = (
                answer.model_dump(mode="json") if answer else None
            )
            mneno.metadata["judge_result"] = (
                judge_result.model_dump(mode="json") if judge_result else None
            )
            mneno.metadata["locomo_result"] = _normalized_result(
                "mneno",
                question,
                values,
                retrieved_ids=metric_ids,
                trace_ids=mneno.trace_ids,
                answer=answer,
                judge_result=judge_result,
                metadata={"raw_output_path": mneno.metadata.get("raw_output_path")},
            ).model_dump(mode="json")
            updated.metrics["mneno"] = _metric_results(values)
    return updated


def _metric_value_map(metrics: list[MetricResult]) -> dict[str, float | int | None]:
    return {metric.name: metric.value for metric in metrics}


def _checkpoint_answer(
    raw_answer: Any,
    config: LOCOMOEvaluationConfig,
    provider: str,
    question: LOCOMOQuestion,
    memories: list[dict[str, Any]],
    retrieved_ids: list[str],
    trace_ids: list[str] | None = None,
) -> AnswerCandidate | None:
    if isinstance(raw_answer, dict):
        try:
            return AnswerCandidate.model_validate(raw_answer)
        except Exception:
            pass
    return _answer_for_mode(
        config,
        provider,
        question,
        _context_text(memories, retrieved_ids),
        trace_ids=trace_ids,
        metadata={"context_source": "checkpoint_retrieval"},
    )


def _load_config(
    config_path: Path | None,
    k: int,
    evaluation_config: LOCOMOEvaluationConfig | None,
) -> LOCOMOEvaluationConfig:
    if evaluation_config is not None:
        config = evaluation_config
    elif config_path is not None:
        config = LOCOMOEvaluationConfig.from_yaml(config_path)
    else:
        config = LOCOMOEvaluationConfig()
    if config.mode != "llm_judge":
        return config
    return config.model_copy(
        update={
            "judge_model": config.judge_model or os.getenv("LITELLM_MODEL"),
            "judge_provider": config.judge_provider or os.getenv("LITELLM_PROVIDER"),
        }
    )


def _build_judge(
    config: LOCOMOEvaluationConfig, results_dir: Path, run_id: str
) -> LOCOMOJudge | None:
    if config.mode != "llm_judge" or not config.judge_model:
        return None
    prompt_dir = results_dir / "locomo" / "judge" / "prompts" / run_id
    response_dir = results_dir / "locomo" / "judge" / "responses" / run_id
    if config.judge_config_path:
        yaml_client = LLMClient.from_yaml(
            config.judge_config_path,
            allow_external_calls=config.allow_external_calls,
        )
        client = LLMClient(
            yaml_client.config.model_copy(
                update={
                    "requests_per_minute": config.external_requests_per_minute,
                    "max_concurrent_requests": config.external_max_concurrent_requests,
                    "max_retries": config.external_retries,
                    "retry_backoff_seconds": config.external_retry_backoff_seconds,
                    "retry_backoff_max_seconds": config.external_retry_backoff_max_seconds,
                    "retry_jitter_seconds": config.external_retry_jitter_seconds,
                }
            ),
            allow_external_calls=config.allow_external_calls,
        )
        return LOCOMOJudge(
            client,
            prompt_version=config.prompt_version,
            save_prompts=config.save_judge_prompts,
            prompt_dir=prompt_dir,
            response_dir=response_dir,
        )
    return LOCOMOJudge(
        LLMClient(
            LLMConfig(
                model=config.judge_model,
                provider=config.judge_provider,
                requests_per_minute=config.external_requests_per_minute,
                max_concurrent_requests=config.external_max_concurrent_requests,
                max_retries=config.external_retries,
                retry_backoff_seconds=config.external_retry_backoff_seconds,
                retry_backoff_max_seconds=config.external_retry_backoff_max_seconds,
                retry_jitter_seconds=config.external_retry_jitter_seconds,
            ),
            allow_external_calls=config.allow_external_calls,
        ),
        prompt_version=config.prompt_version,
        save_prompts=config.save_judge_prompts,
        prompt_dir=prompt_dir,
        response_dir=response_dir,
    )


def _answer_for_mode(
    config: LOCOMOEvaluationConfig,
    provider: str,
    question: LOCOMOQuestion,
    context: str,
    trace_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AnswerCandidate | None:
    if config.mode == "retrieval_only":
        return None
    return generate_answer_from_context(
        provider,
        question.id,
        question.question,
        context,
        trace_ids=trace_ids,
        metadata=metadata,
    )


def _judge_for_mode(
    config: LOCOMOEvaluationConfig,
    judge: LOCOMOJudge | None,
    question: LOCOMOQuestion,
    answer: AnswerCandidate | None,
    results_dir: Path,
    run_id: str,
    provider: str,
) -> JudgeResult | None:
    if config.phase == "predict_only" or config.mode != "llm_judge" or answer is None:
        return None
    if judge is None:
        return JudgeResult(
            question_id=question.id,
            reason="Judge model/configuration is unavailable.",
            model=config.judge_model,
            provider=config.judge_provider,
            prompt_version=config.prompt_version,
            status="skipped",
        )
    provider_judge = LOCOMOJudge(
        judge.client,
        prompt_version=judge.prompt_version,
        save_prompts=judge.save_prompts,
        prompt_dir=(
            results_dir / "locomo" / "judge" / "prompts" / run_id / provider
            if judge.prompt_dir is not None
            else None
        ),
        response_dir=(
            results_dir / "locomo" / "judge" / "responses" / run_id / provider
            if judge.response_dir is not None
            else None
        ),
    )
    gold = question.expected_answers[0] if question.expected_answers else ""
    return provider_judge.evaluate(question.question, gold, answer)


def _apply_answer_metrics(
    values: dict[str, float | int | None],
    question: LOCOMOQuestion,
    answer: AnswerCandidate | None,
    judge_result: JudgeResult | None,
    config: LOCOMOEvaluationConfig,
) -> None:
    if answer is None:
        return
    gold = question.expected_answers[0] if question.expected_answers else ""
    values.update(
        {
            "exact_match": exact_match(answer.answer, gold),
            "normalized_exact_match": normalized_exact_match(answer.answer, gold),
            "token_f1": token_f1(answer.answer, gold),
            "contains_answer": contains_answer(answer.answer, gold),
            "diagnostic_score": answer_diagnostic_score(answer.answer, gold),
            "locomo_official_f1_on_candidate": official_locomo_qa_score(
                answer.answer, gold, question.category
            ),
        }
    )
    category_metric = _category_metric_name(question.category)
    if category_metric:
        values[category_metric] = values["locomo_official_f1_on_candidate"]
    # Answer generation is a local diagnostic, so the durable official_score stays null.
    values["official_score"] = None
    if config.mode == "llm_judge" and judge_result is not None:
        values["judge_score"] = judge_result.score


def _context_text(memories: list[dict[str, Any]], ids: list[str]) -> str:
    selected = set(ids)
    return "\n".join(
        str(memory.get("content", memory.get("text", "")))
        for memory in memories
        if str(memory["id"]) in selected
    )


def _validation_warnings(dataset: LOCOMODataset) -> list[dict[str, object]]:
    return locomo_validation_warnings(dataset)


def _score_labels(metrics: Mapping[str, float | None]) -> dict[str, float | None]:
    return {
        "official_score": metrics.get("official_score"),
        "diagnostic_score": metrics.get("diagnostic_score"),
        "retrieval_diagnostic": metrics.get("retrieval_diagnostic"),
        "judge_score": metrics.get("judge_score"),
    }


def _empty_score_labels() -> dict[str, None]:
    return {
        "official_score": None,
        "diagnostic_score": None,
        "retrieval_diagnostic": None,
        "judge_score": None,
    }


def _judge_summary(
    config: LOCOMOEvaluationConfig, statuses: list[str]
) -> dict[str, Any]:
    if config.mode != "llm_judge":
        return {"status": "not_requested", "model": None, "provider": None}
    if not statuses:
        status = "skipped"
    elif "completed" in statuses:
        status = "completed"
    elif "error" in statuses:
        status = "error"
    else:
        status = "skipped"
    return {
        "status": status,
        "model": config.judge_model,
        "provider": config.judge_provider,
        "prompt_version": config.prompt_version,
    }


def _category_metric_name(category: int | str) -> str | None:
    value = (
        int(category) if isinstance(category, int) or str(category).isdigit() else None
    )
    if value is None:
        return None
    return {
        1: "factual_recall",
        2: "temporal_reasoning",
        3: "multi_hop_reasoning",
        4: "multi_session_reasoning",
        5: "adversarial_answerability",
    }.get(value)


def _metric_description(name: str) -> str:
    return {
        "evidence_precision": "Relevant evidence dialogs divided by retrieved dialogs.",
        "retrieval_hit_rate": "Whether at least one official evidence dialog was retrieved.",
        "retrieved_dialog_count": "Number of dialog turns supplied by the system.",
        "official_score": "Reserved official score label; never inferred from diagnostics.",
        "diagnostic_score": "Local deterministic answer diagnostic.",
        "retrieval_diagnostic": "Evidence-recall retrieval diagnostic.",
        "judge_score": "Optional LiteLLM judge score.",
        "locomo_official_f1_on_candidate": "Released LOCOMO QA scorer applied to the local answer candidate.",
    }.get(name, "LOCOMO evaluation metric.")


def _float_or_none(value: float | int | None) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _format_score(value: Any) -> str:
    return "unavailable" if not isinstance(value, (int, float)) else f"{value:.4f}"


def _should_report_progress(completed: int, total: int) -> bool:
    return completed == 1 or completed == total or completed % 10 == 0


def _report_progress(completed: int, total: int, started_at: float) -> None:
    elapsed = max(time.monotonic() - started_at, 0.001)
    rate = completed / elapsed
    remaining = max(total - completed, 0)
    eta = remaining / rate if rate > 0 else 0.0
    percentage = completed / total * 100 if total else 100.0
    console.print(
        f"[cyan]LOCOMO:[/cyan] {completed}/{total} cases "
        f"({percentage:.1f}%) | elapsed {_format_duration(elapsed)} | "
        f"{rate:.2f} cases/s | ETA {_format_duration(eta)}"
    )


def _format_duration(seconds: float) -> str:
    total_seconds = max(int(seconds), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _write_failure_analysis(
    run: BenchmarkRun,
    results_dir: Path,
    dataset: LOCOMODataset | None = None,
) -> None:
    report = analyze_locomo_failures(run)
    json_path = results_dir / "locomo" / "failures" / "locomo_failures_latest.json"
    markdown_path = results_dir / "locomo" / "locomo_failures_latest.md"
    dashboard_path = (
        results_dir
        / "locomo"
        / "dashboard"
        / "failures"
        / "locomo_failures_latest.json"
    )
    write_failure_report_json(report, json_path)
    write_failure_dashboard_json(report, dashboard_path)
    write_failure_report_markdown(report, markdown_path)
    summary = run.export_metadata.get("locomo")
    if isinstance(summary, dict):
        summary["failure_analysis"] = {
            **locomo_failure_report_summary(report),
            "json_path": str(json_path),
            "report_path": str(markdown_path),
        }
        if dataset is not None:
            deep_dive = analyze_retrieval_failures(
                run,
                report,
                dataset,
                results_dir,
                max_cases=DEFAULT_SAMPLE_SIZE,
            )
            deep_dive_json, deep_dive_report, _ = write_retrieval_deep_dive(
                deep_dive, results_dir
            )
            summary["retrieval_deep_dive"] = {
                "sampled_failure_count": len(deep_dive.sampled_failures),
                "root_causes": {
                    cause: value.model_dump(mode="json")
                    for cause, value in deep_dive.root_causes.items()
                },
                "json_path": str(deep_dive_json),
                "report_path": str(deep_dive_report),
            }


def _write_dashboard_run(run: BenchmarkRun, results_dir: Path) -> None:
    """Write a compact run projection without per-case raw payloads."""

    payload = run.model_dump(mode="json", exclude={"results"})
    summary = run.export_metadata.get("locomo")
    systems = summary.get("systems", {}) if isinstance(summary, dict) else {}
    mneno = systems.get("mneno", {}) if isinstance(systems, dict) else {}
    payload.update(
        {
            "results": [],
            "dashboard_case_count": len(run.results),
            "dashboard_mneno_status": (
                mneno.get("status") if isinstance(mneno, dict) else None
            ),
        }
    )
    save_json(
        results_dir / "locomo" / "dashboard" / "runs" / "locomo_dashboard_latest.json",
        payload,
    )


def _format_counts(value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return "none"
    return ", ".join(f"{name} ({count})" for name, count in value.items())


def _format_worst_cases(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ", ".join(
        f"{item.get('case_id')} / {item.get('provider')} / {item.get('category')}"
        for item in value[:5]
        if isinstance(item, dict)
    )


def _resolve_data_dir(data_dir: Path) -> Path:
    return data_dir / "locomo" if (data_dir / "locomo").is_dir() else data_dir


def _search_ids(result: NormalizedSearchResult) -> list[str]:
    return _extract_ids(result.raw_result)


def _extract_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in (
            "retrieved_memory_ids",
            "selected_memory_ids",
            "memory_ids",
            "included_memory_ids",
            "results",
            "memories",
            "ids",
        ):
            if key in value:
                return _extract_ids(value[key])
        item_id = value.get("id") or value.get("memory_id")
        return [str(item_id)] if item_id is not None else []
    if isinstance(value, list):
        ids: list[str] = []
        for item in value:
            if isinstance(item, str):
                ids.append(item)
            else:
                ids.extend(_extract_ids(item))
        return ids
    return []


def _context_ids(value: Any, kind: str) -> list[str]:
    if kind not in {"included", "excluded"}:
        raise ValueError(f"Unsupported context ID kind: {kind}")
    legacy_ids = _value(value, f"{kind}_memory_ids")
    if legacy_ids is not None:
        return _extract_ids(legacy_ids)
    return _extract_ids(_value(value, kind, []))


def _normalize_ids(values: list[str], reverse_id_map: Mapping[str, str]) -> list[str]:
    return _unique_strings(reverse_id_map.get(value, value) for value in values)


def _internal_memory_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("memory_id", "id", "internal_memory_id"):
            item = value.get(key)
            if item is not None:
                return str(item)
        for key in ("memory", "result", "added_memory"):
            item = _internal_memory_id(value.get(key))
            if item is not None:
                return item
    return None


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        item = str(value)
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _context_tokens(memories: list[dict[str, Any]], retrieved_ids: list[str]) -> int:
    selected = set(retrieved_ids)
    return sum(
        estimate_tokens(str(memory.get("content", memory.get("text", ""))))
        for memory in memories
        if str(memory["id"]) in selected
    )


def _category_name(category: int | str) -> str:
    if isinstance(category, int):
        return CATEGORY_NAMES.get(category, f"category_{category}")
    return str(category).strip().lower().replace(" ", "_")


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "item"


def _cli_config_overrides(**values: Any) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if key in {"checkpoint_dir", "results_dir"}:
            target_key = "output_dir" if key == "results_dir" else key
            overrides[target_key] = str(value)
        else:
            overrides[key] = value
    return overrides


@app.command()
def main(
    data_dir: Path = typer.Option(PROJECT_ROOT / "data", exists=True),
    results_dir: Path | None = typer.Option(None),
    k: int = typer.Option(5, min=1),
    config: Path | None = typer.Option(None),
    mode: LOCOMOEvaluationMode = typer.Option("retrieval_only"),
    judge_model: str | None = typer.Option(None),
    judge_provider: str | None = typer.Option(None),
    max_cases: int | None = typer.Option(None, min=1),
    workers: int = typer.Option(1, min=1, help="Parallel conversation workers."),
    allow_external_calls: bool = typer.Option(False),
    resume: bool | None = typer.Option(
        None, help="Resume compatible completed LOCOMO cases."
    ),
    reuse_failed_checkpoints: bool | None = typer.Option(
        None,
        help="Reuse failed checkpoints instead of retrying them on resume.",
    ),
    phase: LOCOMOExecutionPhase | None = typer.Option(None),
    checkpoint_dir: Path | None = typer.Option(None, help="Explicit checkpoint directory."),
    external_requests_per_minute: int | None = typer.Option(
        None,
        min=1,
        help="Global LiteLLM request start rate for external judge/reranker calls.",
    ),
    external_max_concurrent_requests: int | None = typer.Option(
        None,
        min=1,
        help="Global concurrent external judge/reranker calls.",
    ),
    external_retries: int | None = typer.Option(
        None,
        min=0,
        max=10,
        help="Retries for external judge calls; reranker uses mneno_reranker_retries.",
    ),
    external_retry_backoff_seconds: float | None = typer.Option(None, min=0.0),
    external_retry_backoff_max_seconds: float | None = typer.Option(None, min=0.0),
    external_retry_jitter_seconds: float | None = typer.Option(None, min=0.0),
    allow_malformed_evidence: bool = typer.Option(False),
    mneno_reranker_model: str | None = typer.Option(
        None,
        help="Optional LiteLLM reranker model injected into Mneno.",
        envvar="MNENO_RERANKER_MODEL",
    ),
    mneno_reranker_provider: str | None = typer.Option(
        None,
        help="Provider label recorded for the optional Mneno reranker.",
        envvar="MNENO_RERANKER_PROVIDER",
    ),
    mneno_reranker_api_base: str | None = typer.Option(
        None,
        help="Optional reranker endpoint; credentials still use LITELLM_API_KEY.",
        envvar="MNENO_RERANKER_API_BASE",
    ),
    mneno_reranker_api_key_required: bool = typer.Option(
        True,
        help="Require LITELLM_API_KEY for the Mneno reranker.",
    ),
    mneno_reranker_candidate_limit: int = typer.Option(
        50,
        min=1,
        max=512,
        help="Maximum leading Mneno candidates sent to the reranker.",
    ),
    mneno_reranker_cache_size: int = typer.Option(
        4096,
        min=1,
        help="Per-conversation reranker response cache size.",
    ),
) -> None:
    """Run LOCOMO against local baselines and an optional Mneno installation."""

    if config is not None:
        overrides = _cli_config_overrides(
            resume=resume,
            reuse_failed_checkpoints=reuse_failed_checkpoints,
            phase=phase,
            checkpoint_dir=checkpoint_dir,
            results_dir=results_dir,
            max_cases=max_cases,
            external_requests_per_minute=external_requests_per_minute,
            external_max_concurrent_requests=external_max_concurrent_requests,
            external_retries=external_retries,
            external_retry_backoff_seconds=external_retry_backoff_seconds,
            external_retry_backoff_max_seconds=external_retry_backoff_max_seconds,
            external_retry_jitter_seconds=external_retry_jitter_seconds,
        )
        evaluation_config = LOCOMOEvaluationConfig.from_yaml(config, overrides)
        effective_results_dir = (
            results_dir
            or (Path(evaluation_config.output_dir) if evaluation_config.output_dir else None)
            or PROJECT_ROOT / "results"
        )
    else:
        effective_results_dir = results_dir or PROJECT_ROOT / "results"
        evaluation_config = LOCOMOEvaluationConfig(
            mode=mode,
            judge_model=judge_model,
            judge_provider=judge_provider,
            max_cases=max_cases,
            workers=workers,
            strict_dataset_validation=not allow_malformed_evidence,
            allow_malformed_evidence=allow_malformed_evidence,
            allow_external_calls=allow_external_calls,
            resume=bool(resume),
            reuse_failed_checkpoints=bool(reuse_failed_checkpoints),
            phase=phase or "full",
            checkpoint_dir=str(checkpoint_dir) if checkpoint_dir else None,
            output_dir=str(effective_results_dir),
            external_requests_per_minute=external_requests_per_minute or 60,
            external_max_concurrent_requests=external_max_concurrent_requests or 1,
            external_retries=external_retries if external_retries is not None else 2,
            external_retry_backoff_seconds=(
                external_retry_backoff_seconds
                if external_retry_backoff_seconds is not None
                else 1.0
            ),
            external_retry_backoff_max_seconds=(
                external_retry_backoff_max_seconds
                if external_retry_backoff_max_seconds is not None
                else 30.0
            ),
            external_retry_jitter_seconds=(
                external_retry_jitter_seconds
                if external_retry_jitter_seconds is not None
                else 0.25
            ),
            mneno_reranker_model=mneno_reranker_model,
            mneno_reranker_provider=mneno_reranker_provider,
            mneno_reranker_api_base=mneno_reranker_api_base,
            mneno_reranker_api_key_required=mneno_reranker_api_key_required,
            mneno_reranker_candidate_limit=mneno_reranker_candidate_limit,
            mneno_reranker_cache_size=mneno_reranker_cache_size,
        )
    run_locomo(
        data_dir,
        effective_results_dir,
        k=k,
        evaluation_config=evaluation_config,
    )


if __name__ == "__main__":
    app()
