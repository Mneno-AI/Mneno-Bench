"""Evidence-first retrieval diagnostics for LOCOMO failures.

This module reads completed benchmark artifacts. It does not execute retrieval,
change benchmark scoring, or modify Mneno Core behavior.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, ConfigDict, Field

from benchmarks.common.failures import FailureCase, FailureCategory, FailureReport
from benchmarks.common.schema import BenchmarkResult, BenchmarkRun
from benchmarks.common.utils import load_json, now_iso, save_json
from benchmarks.locomo.loader import load_locomo_dataset
from benchmarks.locomo.schema import LOCOMOConversation, LOCOMODataset, LOCOMOMessage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_SEED = 8
app = typer.Typer(add_completion=False)


class RetrievalRootCause(str, Enum):
    EVIDENCE_NOT_INDEXED = "evidence_not_indexed"
    CANDIDATE_GENERATION_FAILURE = "candidate_generation_failure"
    QUERY_NORMALIZATION_FAILURE = "query_normalization_failure"
    LEXICAL_MISMATCH = "lexical_mismatch"
    SEMANTIC_RETRIEVAL_FAILURE = "semantic_retrieval_failure"
    RANKING_FAILURE = "ranking_failure"
    BUDGET_EXCLUSION = "budget_exclusion"
    SESSION_BIAS_FAILURE = "session_bias_failure"
    LIFECYCLE_FILTER_FAILURE = "lifecycle_filter_failure"
    UNKNOWN = "unknown"


class CountPercentage(BaseModel):
    count: int = Field(ge=0)
    percentage: float = Field(ge=0.0, le=100.0)


class EvidenceMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    text: str | None = None
    content: str | None = None
    session_id: str | None = None
    session_index: int | None = None
    timestamp: str | None = None
    core_memory_id: str | None = None


class RetrievedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    core_memory_id: str
    text: str | None = None
    score: float | None = None
    rank: int | None = None
    selected: bool = False
    session_id: str | None = None
    relevance: float | None = None
    semantic_relevance: float | None = None
    reasons: list[str] = Field(default_factory=list)


class ContextMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    core_memory_id: str
    text: str | None = None
    score: float | None = None
    estimated_tokens: int | None = None
    reason: str | None = None
    session_id: str | None = None


class ContextPackageEvidence(BaseModel):
    included_memories: list[ContextMemory] = Field(default_factory=list)
    excluded_memories: list[ContextMemory] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class TraceEventEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    event_id: str | None = None
    operation: str | None = None
    event_type: str
    memory_id: str | None = None
    evidence_id: str | None = None
    session_id: str | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class TraceInspection(BaseModel):
    trace_ids: list[str] = Field(default_factory=list)
    retrieval_events: list[TraceEventEvidence] = Field(default_factory=list)
    ranking_events: list[TraceEventEvidence] = Field(default_factory=list)
    budget_events: list[TraceEventEvidence] = Field(default_factory=list)
    lifecycle_events: list[TraceEventEvidence] = Field(default_factory=list)
    query_events: list[TraceEventEvidence] = Field(default_factory=list)


class RootCauseClassification(BaseModel):
    root_cause: RetrievalRootCause
    explanation: str
    evidence: list[str] = Field(default_factory=list)


class RetrievalFailureInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    case_id: str
    provider: str
    conversation_id: str
    question_type: str
    category: str
    sessions: list[str] = Field(default_factory=list)
    question: str
    normalized_question: str
    expected_evidence: list[EvidenceMemory] = Field(default_factory=list)
    retrieved_candidates: list[RetrievedCandidate] = Field(default_factory=list)
    context_package: ContextPackageEvidence
    trace: TraceInspection
    normalized_retrieved_ids: list[str] = Field(default_factory=list)
    normalized_included_ids: list[str] = Field(default_factory=list)
    root_cause: RetrievalRootCause = RetrievalRootCause.UNKNOWN
    explanation: str = "Insufficient evidence to classify the retrieval failure."
    classification_evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalStatistics(BaseModel):
    sample_size: int = Field(ge=0)
    expected_evidence_count: int = Field(ge=0)
    retrieved_expected_count: int = Field(ge=0)
    candidate_expected_count: int = Field(ge=0)
    retrieval_recall: float | None = None
    candidate_coverage: float | None = None
    failures_by_root_cause: dict[str, CountPercentage] = Field(default_factory=dict)
    failures_by_conversation: dict[str, CountPercentage] = Field(default_factory=dict)
    failures_by_question_type: dict[str, CountPercentage] = Field(default_factory=dict)
    failures_by_session: dict[str, CountPercentage] = Field(default_factory=dict)
    failures_by_category: dict[str, CountPercentage] = Field(default_factory=dict)


class ImprovementOpportunity(BaseModel):
    title: str
    evidence: list[str] = Field(default_factory=list)
    expected_impact: str
    confidence: str
    suggested_core_area: str


class RetrievalFailureAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark: str
    created_at: str
    provider: str
    total_failures: int = Field(ge=0)
    sampled_failures: list[RetrievalFailureInspection] = Field(default_factory=list)
    root_causes: dict[str, CountPercentage] = Field(default_factory=dict)
    statistics: RetrievalStatistics
    recommendations: list[ImprovementOpportunity] = Field(default_factory=list)
    top_failure_cases: list[RetrievalFailureInspection] = Field(default_factory=list)
    recommended_core_priorities: list[str] = Field(default_factory=list)
    run_id: str | None = None
    deterministic_seed: int = DEFAULT_SEED
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_question_for_analysis(question: str) -> str:
    """Return a transparent diagnostic normalization, not a retrieval query."""

    normalized = unicodedata.normalize("NFKC", question).casefold()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


def sample_retrieval_failures(
    failure_report: FailureReport,
    max_cases: int,
    seed: int,
    *,
    provider: str = "mneno",
    sessions_by_case: Mapping[str, list[str]] | None = None,
) -> list[FailureCase]:
    """Select a deterministic, balanced sample across LOCOMO dimensions."""

    if max_cases <= 0:
        return []
    eligible = [
        failure
        for failure in failure_report.failures
        if failure.provider == provider
        and failure.category == FailureCategory.RETRIEVAL_FAILURE
        and not failure.expected_behavior
    ]
    if len(eligible) <= max_cases:
        return sorted(eligible, key=lambda item: item.id)

    rng = random.Random(seed)
    shuffled = sorted(eligible, key=lambda item: item.id)
    rng.shuffle(shuffled)
    remaining = list(shuffled)
    selected: list[FailureCase] = []
    dimension_counts: dict[str, Counter[str]] = {
        "conversation": Counter(),
        "question_type": Counter(),
        "session": Counter(),
        "category": Counter(),
    }

    while remaining and len(selected) < max_cases:
        best_index = 0
        best_score: tuple[float, ...] | None = None
        for index, failure in enumerate(remaining):
            dimensions = _sampling_dimensions(failure, sessions_by_case)
            score = tuple(
                1.0 / (1 + min(dimension_counts[name][value] for value in values))
                for name, values in dimensions.items()
            )
            if best_score is None or score > best_score:
                best_index = index
                best_score = score
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        for name, values in _sampling_dimensions(chosen, sessions_by_case).items():
            for value in values:
                dimension_counts[name][value] += 1
    return selected


def classify_retrieval_root_cause(
    inspection: RetrievalFailureInspection,
) -> RootCauseClassification:
    """Classify only causes supported by preserved retrieval evidence."""

    expected = [item for item in inspection.expected_evidence if item.text]
    expected_core_ids = {
        item.core_memory_id for item in expected if item.core_memory_id is not None
    }
    selected = [candidate for candidate in inspection.retrieved_candidates if candidate.selected]
    selected_ids = {candidate.core_memory_id for candidate in selected}
    included_ids = {
        item.core_memory_id for item in inspection.context_package.included_memories
    }

    if not expected:
        return RootCauseClassification(
            root_cause=RetrievalRootCause.UNKNOWN,
            explanation="Expected evidence text was unavailable, so retrieval stages cannot be compared safely.",
            evidence=["expected_evidence_text=unavailable"],
        )

    if expected_core_ids & (selected_ids | included_ids):
        return RootCauseClassification(
            root_cause=RetrievalRootCause.UNKNOWN,
            explanation=(
                "Raw artifacts show expected evidence selected or included, but the normalized "
                "benchmark result does not preserve that evidence ID. This is not evidence of a "
                "Core retrieval miss."
            ),
            evidence=[
                f"raw_expected_selected={','.join(sorted(expected_core_ids & (selected_ids | included_ids)))}",
                "normalized_expected_selected=false",
            ],
        )

    lifecycle = _events_for_ids(inspection.trace.lifecycle_events, expected_core_ids)
    if lifecycle:
        return RootCauseClassification(
            root_cause=RetrievalRootCause.LIFECYCLE_FILTER_FAILURE,
            explanation="Trace events explicitly show expected evidence removed by a lifecycle filter.",
            evidence=_event_facts(lifecycle),
        )

    authoritative_trace_ids = set(
        inspection.metadata.get("authoritative_selection_trace_ids", [])
    )
    budget = [
        event
        for event in _events_for_ids(
            inspection.trace.budget_events, expected_core_ids
        )
        if (not authoritative_trace_ids or event.trace_id in authoritative_trace_ids)
        and (
            event.event_type == "budget_exhausted"
            or (
                event.event_type == "context_item_excluded"
                and "budget" in (event.message or "").casefold()
            )
        )
    ]
    if budget:
        return RootCauseClassification(
            root_cause=RetrievalRootCause.BUDGET_EXCLUSION,
            explanation="Expected evidence reached context selection and was explicitly excluded by the context budget.",
            evidence=_event_facts(budget),
        )

    trace_queries = {
        str(event.data.get("query"))
        for event in inspection.trace.query_events
        if event.data.get("query") is not None
    }
    if trace_queries and all(query != inspection.question for query in trace_queries):
        return RootCauseClassification(
            root_cause=RetrievalRootCause.QUERY_NORMALIZATION_FAILURE,
            explanation="The query recorded by retrieval differs from the raw benchmark question.",
            evidence=[f"raw_query={inspection.question}", *[f"trace_query={q}" for q in sorted(trace_queries)]],
        )

    expected_candidates = [
        candidate
        for candidate in inspection.retrieved_candidates
        if candidate.core_memory_id in expected_core_ids
    ]
    if expected_candidates:
        displacement = _session_displacement(inspection, expected_candidates, selected)
        if displacement:
            return RootCauseClassification(
                root_cause=RetrievalRootCause.SESSION_BIAS_FAILURE,
                explanation="An explicit active-session boost displaced expected evidence from the final result set.",
                evidence=displacement,
            )

        if all(
            candidate.relevance == 0
            and not any(reason.startswith("Matched query term:") for reason in candidate.reasons)
            for candidate in expected_candidates
        ) and _semantic_stage_used(inspection) is False:
            return RootCauseClassification(
                root_cause=RetrievalRootCause.LEXICAL_MISMATCH,
                explanation="Expected evidence was a candidate, received zero lexical relevance, and semantic retrieval was explicitly skipped.",
                evidence=[
                    *[f"{candidate.id}:lexical_relevance=0" for candidate in expected_candidates],
                    "semantic_stage_used=false",
                ],
            )

        semantic_values = [
            candidate.semantic_relevance
            for candidate in expected_candidates
            if candidate.semantic_relevance is not None
        ]
        if _semantic_stage_used(inspection) is True and semantic_values and max(semantic_values) <= 0:
            return RootCauseClassification(
                root_cause=RetrievalRootCause.SEMANTIC_RETRIEVAL_FAILURE,
                explanation="Expected evidence was a candidate but received no semantic relevance in an active semantic stage.",
                evidence=[f"max_semantic_relevance={max(semantic_values):.6f}"],
            )

        return RootCauseClassification(
            root_cause=RetrievalRootCause.RANKING_FAILURE,
            explanation="Expected evidence appeared in the scored candidate set but was not selected.",
            evidence=[
                f"candidate_ids={','.join(sorted(expected_core_ids))}",
                f"selected_ids={','.join(sorted(selected_ids)) or 'none'}",
            ],
        )

    stored_count = _trace_count(inspection.trace.retrieval_events, "memories_loaded", "memory_count")
    candidate_count = _trace_count(
        inspection.trace.retrieval_events, "candidate_filtering", "candidate_count"
    )
    explicitly_indexed = set(inspection.metadata.get("indexed_evidence_ids", []))
    if explicitly_indexed & {item.evidence_id for item in expected}:
        return RootCauseClassification(
            root_cause=RetrievalRootCause.CANDIDATE_GENERATION_FAILURE,
            explanation="Expected evidence is explicitly recorded as indexed but never appears in the candidate set.",
            evidence=["indexed_expected_evidence=true", "candidate_expected_evidence=false"],
        )
    if stored_count is not None and candidate_count == stored_count:
        return RootCauseClassification(
            root_cause=RetrievalRootCause.EVIDENCE_NOT_INDEXED,
            explanation="All stored memories entered candidate scoring, but expected evidence was absent from that complete inventory.",
            evidence=[f"stored_count={stored_count}", f"candidate_count={candidate_count}"],
        )
    return RootCauseClassification(
        root_cause=RetrievalRootCause.UNKNOWN,
        explanation=(
            "Expected evidence was absent from the observable candidate set, but the artifacts do not distinguish "
            "indexing, lifecycle filtering, or candidate-generation causes."
        ),
        evidence=[
            f"stored_count={stored_count if stored_count is not None else 'unavailable'}",
            f"candidate_count={candidate_count if candidate_count is not None else 'unavailable'}",
        ],
    )


def aggregate_retrieval_statistics(
    inspections: list[RetrievalFailureInspection],
) -> RetrievalStatistics:
    expected_count = sum(len(item.expected_evidence) for item in inspections)
    retrieved_count = 0
    candidate_count = 0
    for inspection in inspections:
        selected_ids = {
            candidate.id for candidate in inspection.retrieved_candidates if candidate.selected
        }
        candidate_ids = {candidate.id for candidate in inspection.retrieved_candidates}
        expected_ids = {item.evidence_id for item in inspection.expected_evidence}
        retrieved_count += len(expected_ids & selected_ids)
        candidate_count += len(expected_ids & candidate_ids)
    return RetrievalStatistics(
        sample_size=len(inspections),
        expected_evidence_count=expected_count,
        retrieved_expected_count=retrieved_count,
        candidate_expected_count=candidate_count,
        retrieval_recall=_ratio(retrieved_count, expected_count),
        candidate_coverage=_ratio(candidate_count, expected_count),
        failures_by_root_cause=_distribution(item.root_cause.value for item in inspections),
        failures_by_conversation=_distribution(item.conversation_id for item in inspections),
        failures_by_question_type=_distribution(item.question_type for item in inspections),
        failures_by_session=_distribution(
            session for item in inspections for session in (item.sessions or ["unknown"])
        ),
        failures_by_category=_distribution(item.category for item in inspections),
    )


def analyze_retrieval_failures(
    run: BenchmarkRun,
    failure_report: FailureReport,
    dataset: LOCOMODataset,
    results_dir: str | Path,
    *,
    provider: str = "mneno",
    max_cases: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
) -> RetrievalFailureAnalysis:
    results_root = Path(results_dir)
    context = _dataset_context(dataset)
    retrieval_failures = [
        failure
        for failure in failure_report.failures
        if failure.provider == provider
        and failure.category == FailureCategory.RETRIEVAL_FAILURE
        and not failure.expected_behavior
    ]
    sampled = sample_retrieval_failures(
        failure_report,
        max_cases,
        seed,
        provider=provider,
        sessions_by_case=context.sessions_by_case,
    )
    results_by_case = {result.case.id: result for result in run.results}
    inspections = [
        _inspect_failure(
            failure,
            results_by_case.get(failure.case_id),
            context,
            results_root,
            run.run_id,
        )
        for failure in sampled
    ]
    statistics = aggregate_retrieval_statistics(inspections)
    recommendations = _improvement_opportunities(inspections, statistics)
    return RetrievalFailureAnalysis(
        benchmark="locomo",
        created_at=run.finished_at or now_iso(),
        provider=provider,
        total_failures=len(retrieval_failures),
        sampled_failures=inspections,
        root_causes=statistics.failures_by_root_cause,
        statistics=statistics,
        recommendations=recommendations,
        top_failure_cases=_top_informative_failures(inspections, 25),
        recommended_core_priorities=[opportunity.title for opportunity in recommendations[:5]],
        run_id=run.run_id,
        deterministic_seed=seed,
        metadata={
            "format": "mneno-bench.locomo-retrieval-deep-dive",
            "version": 1,
            "diagnostics_only": True,
            "classification_policy": "evidence_only_unknown_when_uncertain",
        },
    )


def write_retrieval_deep_dive(
    analysis: RetrievalFailureAnalysis,
    results_dir: str | Path,
) -> tuple[Path, Path, Path]:
    root = Path(results_dir)
    directory = root / "locomo" / "deep_dive"
    json_path = directory / "retrieval_deep_dive_latest.json"
    markdown_path = directory / "retrieval_deep_dive_latest.md"
    dashboard_path = (
        root
        / "locomo"
        / "dashboard"
        / "deep_dive"
        / "retrieval_deep_dive_latest.json"
    )
    save_json(json_path, analysis.model_dump(mode="json"))
    save_json(dashboard_path, _dashboard_projection(analysis))
    _write_markdown(analysis, markdown_path)
    return json_path, markdown_path, dashboard_path


class _DatasetContext:
    def __init__(self, dataset: LOCOMODataset) -> None:
        self.conversations = dataset.conversation_by_id
        self.messages_by_conversation = {
            conversation.id: conversation.message_by_id
            for conversation in dataset.conversations
        }
        self.sessions_by_case = {
            question.id: sorted(
                {
                    message.session_id
                    for evidence_id in question.evidence_ids
                    if (message := conversation.message_by_id.get(evidence_id)) is not None
                }
            )
            for conversation in dataset.conversations
            for question in conversation.questions
        }


def _dataset_context(dataset: LOCOMODataset) -> _DatasetContext:
    return _DatasetContext(dataset)


def _inspect_failure(
    failure: FailureCase,
    result: BenchmarkResult | None,
    context: _DatasetContext,
    results_dir: Path,
    run_id: str,
) -> RetrievalFailureInspection:
    conversation_id = str(failure.metadata.get("conversation_id") or failure.case_id.split(":", 1)[0])
    conversation = context.conversations.get(conversation_id)
    message_index = context.messages_by_conversation.get(conversation_id, {})
    expected = [_expected_memory(evidence_id, message_index.get(evidence_id)) for evidence_id in failure.expected_ids]
    raw = _load_case_raw_output(result, results_dir, run_id, failure.case_id)
    raw_memories = _raw_context_memories(raw)
    content_map = _content_map(conversation)
    core_to_dataset: dict[str, str] = {}
    dataset_to_core: dict[str, str] = {}
    for item in raw_memories:
        core_id = str(item.get("memory_id", ""))
        dataset_id = content_map.get(_canonical_content(str(item.get("content", ""))))
        if core_id and dataset_id:
            core_to_dataset[core_id] = dataset_id
            dataset_to_core[dataset_id] = core_id
    expected = [
        item.model_copy(update={"core_memory_id": dataset_to_core.get(item.evidence_id)})
        for item in expected
    ]
    traces = _load_case_traces(result, results_dir, run_id, failure.case_id)
    score_events = _score_events(traces)
    selected_ids = _selected_core_ids(raw, traces)
    candidates = _retrieved_candidates(
        raw_memories,
        selected_ids,
        score_events,
        core_to_dataset,
        message_index,
        set(failure.expected_ids),
    )
    context_package = _context_package(
        raw, core_to_dataset, message_index, set(failure.expected_ids)
    )
    trace_inspection = _trace_inspection(
        traces,
        core_to_dataset,
        {item.core_memory_id for item in expected if item.core_memory_id} | selected_ids,
    )
    category = str(failure.metadata.get("benchmark_category") or "unknown")
    inspection = RetrievalFailureInspection(
        id=failure.id,
        case_id=failure.case_id,
        provider=failure.provider,
        conversation_id=conversation_id,
        question_type=category,
        category=category,
        sessions=context.sessions_by_case.get(failure.case_id, []),
        question=failure.query,
        normalized_question=normalize_question_for_analysis(failure.query),
        expected_evidence=expected,
        retrieved_candidates=candidates,
        context_package=context_package,
        trace=trace_inspection,
        normalized_retrieved_ids=failure.retrieved_ids,
        normalized_included_ids=failure.included_ids,
        metadata={
            "raw_output_available": bool(raw),
            "trace_count": len(traces),
            "candidate_inventory_count": len(raw_memories),
            "reported_candidates": "selected_and_expected",
            "reported_context_exclusions": "expected_only",
            "authoritative_selection_trace_ids": _authoritative_trace_ids(raw),
        },
    )
    classification = classify_retrieval_root_cause(inspection)
    return inspection.model_copy(
        update={
            "root_cause": classification.root_cause,
            "explanation": classification.explanation,
            "classification_evidence": classification.evidence,
        }
    )


def _expected_memory(evidence_id: str, message: LOCOMOMessage | None) -> EvidenceMemory:
    if message is None:
        return EvidenceMemory(evidence_id=evidence_id)
    content = message.as_benchmark_memory("unused")["content"]
    return EvidenceMemory(
        evidence_id=evidence_id,
        text=message.text,
        content=str(content),
        session_id=message.session_id,
        session_index=message.session_index,
        timestamp=message.timestamp,
    )


def _content_map(conversation: LOCOMOConversation | None) -> dict[str, str]:
    if conversation is None:
        return {}
    mapping: dict[str, str] = {}
    duplicates: set[str] = set()
    for message in conversation.messages:
        content = str(message.as_benchmark_memory(conversation.id)["content"])
        key = _canonical_content(content)
        if key in mapping:
            duplicates.add(key)
        mapping[key] = message.id
    return {key: value for key, value in mapping.items() if key not in duplicates}


def _canonical_content(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _load_case_raw_output(
    result: BenchmarkResult | None,
    results_dir: Path,
    run_id: str,
    case_id: str,
) -> dict[str, Any]:
    candidates: list[Path] = []
    if result and result.mneno_result:
        path = result.mneno_result.metadata.get("raw_output_path")
        if path:
            candidates.append(_local_artifact_path(str(path), results_dir))
    candidates.append(results_dir / "locomo" / "raw" / run_id / f"{_safe_name(case_id)}.json")
    for path in candidates:
        if path.is_file():
            value = load_json(path)
            return value if isinstance(value, dict) else {}
    return {}


def _load_case_traces(
    result: BenchmarkResult | None,
    results_dir: Path,
    run_id: str,
    case_id: str,
) -> list[dict[str, Any]]:
    paths: list[Path] = []
    if result and result.mneno_result:
        for value in result.mneno_result.metadata.get("trace_locations", []):
            paths.append(_local_artifact_path(str(value), results_dir))
    if not paths:
        pattern = f"{run_id}-{_safe_name(case_id)}-*.json"
        paths.extend(sorted((results_dir / "locomo" / "traces").glob(pattern)))
    traces: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
        value = load_json(path)
        if isinstance(value, dict) and isinstance(value.get("trace"), dict):
            traces.append(value["trace"])
    return traces


def _local_artifact_path(value: str, results_dir: Path) -> Path:
    path = Path(value)
    if path.is_file():
        return path
    parts = path.parts
    if "results" in parts:
        index = parts.index("results")
        return results_dir.joinpath(*parts[index + 1 :])
    return path


def _raw_context_memories(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    built = _mapping(raw.get("built_context"))
    return [
        item
        for key in ("included", "excluded")
        for item in _dict_list(built.get(key))
    ]


def _selected_core_ids(raw: Mapping[str, Any], traces: list[dict[str, Any]]) -> set[str]:
    search = _mapping(_mapping(raw.get("search")).get("raw_result"))
    selected = {str(item) for item in _list(search.get("selected_memory_ids"))}
    if selected:
        return selected
    for trace in traces:
        for event in _dict_list(trace.get("events")):
            if event.get("event_type") == "final_results_selected":
                selected.update(str(item) for item in _list(_mapping(event.get("data")).get("memory_ids")))
    return selected


def _authoritative_trace_ids(raw: Mapping[str, Any]) -> list[str]:
    values = [
        _mapping(raw.get("search")).get("trace_id"),
        _mapping(raw.get("built_context")).get("trace_id"),
    ]
    return [str(value) for value in values if value]


def _score_events(traces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    for trace in traces:
        for event in _dict_list(trace.get("events")):
            if event.get("event_type") != "score_calculated" or not event.get("memory_id"):
                continue
            scores[str(event["memory_id"])] = _mapping(event.get("data"))
    return scores


def _retrieved_candidates(
    raw_memories: list[dict[str, Any]],
    selected_ids: set[str],
    score_events: Mapping[str, dict[str, Any]],
    core_to_dataset: Mapping[str, str],
    message_index: Mapping[str, LOCOMOMessage],
    expected_ids: set[str],
) -> list[RetrievedCandidate]:
    by_core = {str(item.get("memory_id")): item for item in raw_memories}
    ordered_ids = sorted(
        by_core,
        key=lambda core_id: (
            core_id not in selected_ids,
            -_float(_mapping(score_events.get(core_id)).get("total"), default=-1.0),
            core_id,
        ),
    )
    result: list[RetrievedCandidate] = []
    selected_rank = 0
    for core_id in ordered_ids:
        raw = by_core[core_id]
        score = _mapping(score_events.get(core_id))
        dataset_id = core_to_dataset.get(core_id, core_id)
        if core_id not in selected_ids and dataset_id not in expected_ids:
            continue
        if core_id in selected_ids:
            selected_rank += 1
        message = message_index.get(dataset_id)
        result.append(
            RetrievedCandidate(
                id=dataset_id,
                core_memory_id=core_id,
                text=message.text if message else str(raw.get("content") or "") or None,
                score=_optional_float(score.get("total", raw.get("score"))),
                rank=selected_rank if core_id in selected_ids else None,
                selected=core_id in selected_ids,
                session_id=message.session_id if message else None,
                relevance=_optional_float(score.get("relevance")),
                semantic_relevance=_optional_float(score.get("semantic_relevance")),
                reasons=[str(item) for item in _list(score.get("reasons"))],
            )
        )
    return result


def _context_package(
    raw: Mapping[str, Any],
    core_to_dataset: Mapping[str, str],
    message_index: Mapping[str, LOCOMOMessage],
    expected_ids: set[str],
) -> ContextPackageEvidence:
    built = _mapping(raw.get("built_context"))

    def convert(item: dict[str, Any]) -> ContextMemory:
        core_id = str(item.get("memory_id", ""))
        dataset_id = core_to_dataset.get(core_id, core_id)
        message = message_index.get(dataset_id)
        return ContextMemory(
            id=dataset_id,
            core_memory_id=core_id,
            text=message.text if message else str(item.get("content") or "") or None,
            score=_optional_float(item.get("score")),
            estimated_tokens=_optional_int(item.get("estimated_tokens")),
            reason=str(item.get("reason")) if item.get("reason") is not None else None,
            session_id=message.session_id if message else None,
        )

    return ContextPackageEvidence(
        included_memories=[convert(item) for item in _dict_list(built.get("included"))],
        excluded_memories=[
            convert(item)
            for item in _dict_list(built.get("excluded"))
            if core_to_dataset.get(str(item.get("memory_id", ""))) in expected_ids
        ],
        stats=_mapping(built.get("stats")),
    )


def _trace_inspection(
    traces: list[dict[str, Any]],
    core_to_dataset: Mapping[str, str],
    relevant_ids: set[str],
) -> TraceInspection:
    groups: dict[str, list[TraceEventEvidence]] = defaultdict(list)
    retrieval_types = {
        "memories_loaded",
        "inactive_filtering_applied",
        "candidate_filtering",
        "semantic_stage",
        "reranker_stage",
        "session_boost_stage",
        "final_results_selected",
        "context_candidates",
    }
    ranking_types = {"score_calculated", "session_boost_applied", "context_candidate_scored"}
    budget_types = {"context_budget_calculated", "budget_exhausted", "context_item_excluded", "context_stats"}
    lifecycle_types = {"inactive_memory_filtered", "archived_memory_filtered", "superseded_memory_filtered", "lifecycle_filter_applied"}
    for trace in traces:
        trace_id = str(trace.get("id", ""))
        for raw in _dict_list(trace.get("events")):
            event_type = str(raw.get("event_type", "unknown"))
            memory_id = str(raw["memory_id"]) if raw.get("memory_id") else None
            event = TraceEventEvidence(
                trace_id=trace_id,
                event_id=str(raw["id"]) if raw.get("id") else None,
                operation=str(raw["operation"]) if raw.get("operation") else None,
                event_type=event_type,
                memory_id=memory_id,
                evidence_id=core_to_dataset.get(memory_id) if memory_id else None,
                session_id=str(raw["session_id"]) if raw.get("session_id") else None,
                message=str(raw["message"]) if raw.get("message") else None,
                data=_mapping(raw.get("data")),
            )
            if event_type in retrieval_types:
                groups["retrieval"].append(event)
            if event_type in ranking_types and (memory_id is None or memory_id in relevant_ids):
                groups["ranking"].append(event)
            if event_type in budget_types and (memory_id is None or memory_id in relevant_ids):
                groups["budget"].append(event)
            if event_type in lifecycle_types and (memory_id is None or memory_id in relevant_ids):
                groups["lifecycle"].append(event)
            if event_type in {"query_received", "operation_started"}:
                groups["query"].append(event)
    return TraceInspection(
        trace_ids=[str(trace.get("id")) for trace in traces if trace.get("id")],
        retrieval_events=groups["retrieval"],
        ranking_events=groups["ranking"],
        budget_events=groups["budget"],
        lifecycle_events=groups["lifecycle"],
        query_events=groups["query"],
    )


def _session_displacement(
    inspection: RetrievalFailureInspection,
    expected: list[RetrievedCandidate],
    selected: list[RetrievedCandidate],
) -> list[str]:
    boosts = {
        event.memory_id: _float(event.data.get("boost"), default=0.0)
        for event in inspection.trace.ranking_events
        if event.event_type == "session_boost_applied" and event.memory_id
    }
    expected_scores = [item.score for item in expected if item.score is not None]
    selected_scores = [item for item in selected if item.score is not None]
    if not expected_scores or not selected_scores:
        return []
    best_expected = max(expected_scores)
    displaced = [
        item
        for item in selected_scores
        if boosts.get(item.core_memory_id, 0.0) > 0
        and item.score is not None
        and item.score - boosts[item.core_memory_id] < best_expected <= item.score
    ]
    if not displaced:
        return []
    weakest = min(displaced, key=lambda item: item.score or 0.0)
    boost = boosts[weakest.core_memory_id]
    return [
        f"expected_score={best_expected:.6f}",
        f"selected_memory={weakest.id}",
        f"selected_score={weakest.score:.6f}",
        f"session_boost={boost:.6f}",
        f"selected_score_without_boost={(weakest.score or 0.0) - boost:.6f}",
    ]


def _semantic_stage_used(inspection: RetrievalFailureInspection) -> bool | None:
    values = [
        event.data.get("used")
        for event in inspection.trace.retrieval_events
        if event.event_type == "semantic_stage" and isinstance(event.data.get("used"), bool)
    ]
    return values[-1] if values else None


def _events_for_ids(events: list[TraceEventEvidence], ids: set[str]) -> list[TraceEventEvidence]:
    return [event for event in events if event.memory_id in ids]


def _event_facts(events: list[TraceEventEvidence]) -> list[str]:
    return [
        f"{event.trace_id}:{event.event_type}:{event.memory_id or 'none'}:{event.message or ''}"
        for event in events
    ]


def _trace_count(
    events: list[TraceEventEvidence], event_type: str, key: str
) -> int | None:
    for event in events:
        if event.event_type == event_type and isinstance(event.data.get(key), int):
            return int(event.data[key])
    return None


def _improvement_opportunities(
    inspections: list[RetrievalFailureInspection],
    statistics: RetrievalStatistics,
) -> list[ImprovementOpportunity]:
    counts = Counter(item.root_cause for item in inspections)
    opportunities: list[ImprovementOpportunity] = []
    definitions = {
        RetrievalRootCause.SESSION_BIAS_FAILURE: (
            "Session-aware ranking",
            "Revisit how active-session boosts interact with cross-session factual and temporal evidence.",
            "high",
            "Retrieval ranking and session weighting",
        ),
        RetrievalRootCause.RANKING_FAILURE: (
            "Candidate ranking",
            "Improve ordering when expected evidence is present in the candidate pool but below the selection cutoff.",
            "high",
            "Retrieval ranking",
        ),
        RetrievalRootCause.LEXICAL_MISMATCH: (
            "Lexical matching coverage",
            "Reduce misses where candidate evidence receives no lexical relevance and no semantic stage is available.",
            "high",
            "Query matching and candidate scoring",
        ),
        RetrievalRootCause.SEMANTIC_RETRIEVAL_FAILURE: (
            "Semantic retrieval quality",
            "Improve semantic evidence recall for candidates with weak lexical overlap.",
            "medium",
            "Semantic retrieval",
        ),
        RetrievalRootCause.BUDGET_EXCLUSION: (
            "Context budget allocation",
            "Retain high-value evidence that reaches context selection but is removed by budget policy.",
            "medium",
            "Context budgeting",
        ),
        RetrievalRootCause.CANDIDATE_GENERATION_FAILURE: (
            "Candidate generation coverage",
            "Increase candidate coverage for evidence that is indexed but never reaches scoring.",
            "high",
            "Candidate generation",
        ),
        RetrievalRootCause.EVIDENCE_NOT_INDEXED: (
            "Index completeness",
            "Ensure benchmark memories remain present and searchable after ingestion.",
            "high",
            "Memory indexing",
        ),
        RetrievalRootCause.LIFECYCLE_FILTER_FAILURE: (
            "Lifecycle filter precision",
            "Prevent relevant active evidence from being removed by lifecycle state filters.",
            "medium",
            "Lifecycle filtering",
        ),
        RetrievalRootCause.QUERY_NORMALIZATION_FAILURE: (
            "Query normalization",
            "Preserve meaning and key entities across query preprocessing.",
            "medium",
            "Query normalization",
        ),
    }
    for cause, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].value)):
        if cause not in definitions:
            continue
        title, impact, confidence, area = definitions[cause]
        examples = [item.case_id for item in inspections if item.root_cause == cause][:5]
        opportunities.append(
            ImprovementOpportunity(
                title=title,
                evidence=[
                    f"{count}/{len(inspections)} sampled failures ({_percentage(count, len(inspections)):.1f}%)",
                    f"example_cases={','.join(examples)}",
                ],
                expected_impact=impact,
                confidence=confidence,
                suggested_core_area=area,
            )
        )
    unknown = counts[RetrievalRootCause.UNKNOWN]
    if unknown:
        opportunities.append(
            ImprovementOpportunity(
                title="Memory identity and trace observability",
                evidence=[
                    f"{unknown}/{len(inspections)} sampled failures remain unknown",
                    "Unknown is retained where artifacts cannot distinguish indexing, filtering, and candidate generation.",
                ],
                expected_impact="Make future retrieval failures classifiable without changing retrieval behavior.",
                confidence="high",
                suggested_core_area="Trace exports and memory identity metadata",
            )
        )
    if statistics.candidate_coverage is not None:
        opportunities.append(
            ImprovementOpportunity(
                title="Candidate coverage measurement",
                evidence=[f"sample_candidate_coverage={statistics.candidate_coverage:.4f}"],
                expected_impact="Track whether future Core changes improve recall before ranking and context selection.",
                confidence="high",
                suggested_core_area="Retrieval diagnostics",
            )
        )
    return opportunities


def _top_informative_failures(
    inspections: list[RetrievalFailureInspection], limit: int
) -> list[RetrievalFailureInspection]:
    cause_counts: Counter[RetrievalRootCause] = Counter()
    conversation_counts: Counter[str] = Counter()
    ordered = sorted(
        inspections,
        key=lambda item: (
            item.root_cause == RetrievalRootCause.UNKNOWN,
            -len(item.classification_evidence),
            -len(item.trace.trace_ids),
            item.case_id,
        ),
    )
    selected: list[RetrievalFailureInspection] = []
    while ordered and len(selected) < limit:
        best = min(
            ordered,
            key=lambda item: (
                cause_counts[item.root_cause],
                conversation_counts[item.conversation_id],
                item.root_cause == RetrievalRootCause.UNKNOWN,
                item.case_id,
            ),
        )
        ordered.remove(best)
        selected.append(best)
        cause_counts[best.root_cause] += 1
        conversation_counts[best.conversation_id] += 1
    return selected


def _dashboard_projection(analysis: RetrievalFailureAnalysis) -> dict[str, Any]:
    payload = analysis.model_dump(mode="json")
    payload["sampled_failures"] = [
        _compact_inspection(item) for item in analysis.top_failure_cases
    ]
    payload["top_failure_cases"] = []
    payload["metadata"] = {**payload["metadata"], "dashboard_projection": True}
    return payload


def _compact_inspection(item: RetrievalFailureInspection) -> dict[str, Any]:
    payload = item.model_dump(mode="json")
    expected_ids = {memory.evidence_id for memory in item.expected_evidence}
    payload["retrieved_candidates"] = [
        candidate.model_dump(mode="json")
        for candidate in item.retrieved_candidates
        if candidate.selected or candidate.id in expected_ids
    ][:15]
    payload["context_package"] = {
        "included_memories": [],
        "excluded_memories": [],
        "stats": item.context_package.stats,
    }
    payload["trace"] = {"trace_ids": item.trace.trace_ids}
    payload["metadata"] = {}
    return payload


def _write_markdown(analysis: RetrievalFailureAnalysis, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Retrieval Deep Dive",
        "",
        "## Summary",
        "",
        f"- Benchmark: **{analysis.benchmark}**",
        f"- Provider: **{analysis.provider}**",
        f"- Run ID: `{analysis.run_id or 'unknown'}`",
        f"- Total retrieval failures: **{analysis.total_failures}**",
        f"- Sampled failures: **{len(analysis.sampled_failures)}**",
        f"- Retrieval recall in sample: **{_format_ratio(analysis.statistics.retrieval_recall)}**",
        f"- Candidate coverage in sample: **{_format_ratio(analysis.statistics.candidate_coverage)}**",
        "",
        "## Top Root Causes",
        "",
        *_count_percentage_table(analysis.root_causes, "Root cause"),
        "",
        "## Statistics",
        "",
        "### By Conversation",
        "",
        *_count_percentage_table(analysis.statistics.failures_by_conversation, "Conversation"),
        "",
        "### By Question Type",
        "",
        *_count_percentage_table(analysis.statistics.failures_by_question_type, "Question type"),
        "",
        "### By Session",
        "",
        *_count_percentage_table(analysis.statistics.failures_by_session, "Session"),
        "",
        "## Top Failure Cases",
        "",
    ]
    for index, failure in enumerate(analysis.top_failure_cases, start=1):
        lines.extend(
            [
                f"### {index}. {failure.case_id}",
                "",
                f"- Question: {failure.question}",
                f"- Expected evidence: `{_evidence_summary(failure.expected_evidence)}`",
                f"- Retrieved evidence: `{_candidate_summary(failure.retrieved_candidates)}`",
                f"- Root cause: **{failure.root_cause.value}**",
                f"- Trace IDs: `{', '.join(failure.trace.trace_ids) or 'none'}`",
                f"- Explanation: {failure.explanation}",
                "",
            ]
        )
    lines.extend(["## Improvement Opportunities", ""])
    for opportunity in analysis.recommendations:
        lines.extend(
            [
                f"### {opportunity.title}",
                "",
                f"- Evidence: {'; '.join(opportunity.evidence)}",
                f"- Expected impact: {opportunity.expected_impact}",
                f"- Confidence: **{opportunity.confidence}**",
                f"- Suggested Core area: {opportunity.suggested_core_area}",
                "",
            ]
        )
    lines.extend(["## Recommended Core Priorities", ""])
    if analysis.recommended_core_priorities:
        lines.extend(
            f"{index}. {priority}"
            for index, priority in enumerate(analysis.recommended_core_priorities, start=1)
        )
    else:
        lines.append("No Core priority is supported by the current evidence.")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _sampling_dimensions(
    failure: FailureCase,
    sessions_by_case: Mapping[str, list[str]] | None,
) -> dict[str, list[str]]:
    conversation = str(failure.metadata.get("conversation_id") or failure.case_id.split(":", 1)[0])
    question_type = str(
        failure.metadata.get("question_type")
        or failure.metadata.get("benchmark_category")
        or "unknown"
    )
    category = str(failure.metadata.get("benchmark_category") or failure.category.value)
    sessions = list((sessions_by_case or {}).get(failure.case_id, []))
    if not sessions:
        sessions = [str(failure.metadata.get("session_id") or "unknown")]
    return {
        "conversation": [conversation],
        "question_type": [question_type],
        "session": sessions,
        "category": [category],
    }


def _distribution(values: Iterable[str]) -> dict[str, CountPercentage]:
    counts = Counter(values)
    total = sum(counts.values())
    return {
        key: CountPercentage(count=count, percentage=_percentage(count, total))
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }


def _percentage(count: int, total: int) -> float:
    return round(count / total * 100, 2) if total else 0.0


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in _list(value) if isinstance(item, Mapping)]


def _float(value: Any, *, default: float) -> float:
    return float(value) if isinstance(value, int | float) else default


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "item"


def _count_percentage_table(
    values: Mapping[str, CountPercentage], label: str
) -> list[str]:
    lines = [f"| {label} | Count | Percentage |", "| --- | ---: | ---: |"]
    if not values:
        return [*lines, "| None | 0 | 0.0% |"]
    return [
        *lines,
        *[
            f"| {key} | {value.count} | {value.percentage:.1f}% |"
            for key, value in values.items()
        ],
    ]


def _format_ratio(value: float | None) -> str:
    return "unavailable" if value is None else f"{value * 100:.1f}%"


def _evidence_summary(values: list[EvidenceMemory]) -> str:
    return ", ".join(item.evidence_id for item in values) or "none"


def _candidate_summary(values: list[RetrievedCandidate]) -> str:
    return ", ".join(item.id for item in values if item.selected) or "none"


@app.command()
def main(
    run_path: Path = typer.Option(
        PROJECT_ROOT / "results" / "locomo" / "locomo_latest.json",
        exists=True,
    ),
    failure_report_path: Path = typer.Option(
        PROJECT_ROOT
        / "results"
        / "locomo"
        / "failures"
        / "locomo_failures_latest.json",
        exists=True,
    ),
    data_dir: Path = typer.Option(PROJECT_ROOT / "data" / "locomo", exists=True),
    results_dir: Path = typer.Option(PROJECT_ROOT / "results"),
    max_cases: int = typer.Option(DEFAULT_SAMPLE_SIZE, min=1),
    seed: int = typer.Option(DEFAULT_SEED),
    provider: str = typer.Option("mneno"),
) -> None:
    """Generate a diagnostics-only retrieval deep dive from local artifacts."""

    run = BenchmarkRun.model_validate(load_json(run_path))
    failure_report = FailureReport.model_validate(load_json(failure_report_path))
    dataset = load_locomo_dataset(data_dir, allow_malformed_evidence=True)
    analysis = analyze_retrieval_failures(
        run,
        failure_report,
        dataset,
        results_dir,
        provider=provider,
        max_cases=max_cases,
        seed=seed,
    )
    json_path, markdown_path, _ = write_retrieval_deep_dive(analysis, results_dir)
    typer.echo(f"Result: {json_path}")
    typer.echo(f"Report: {markdown_path}")


if __name__ == "__main__":
    app()
