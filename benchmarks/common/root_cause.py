"""Evidence-based failure classification and trace signal extraction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from benchmarks.common.failures import (
    FailureCase,
    FailureCategory,
    FailureSeverity,
    is_baseline_provider,
)


SEVERITY_BY_CATEGORY = {
    FailureCategory.RETRIEVAL_FAILURE: FailureSeverity.HIGH,
    FailureCategory.RANKING_FAILURE: FailureSeverity.MEDIUM,
    FailureCategory.CONTEXT_BUDGET_FAILURE: FailureSeverity.HIGH,
    FailureCategory.LIFECYCLE_FILTER_FAILURE: FailureSeverity.HIGH,
    FailureCategory.SESSION_CONTINUITY_FAILURE: FailureSeverity.HIGH,
    FailureCategory.CONFLICT_RESOLUTION_FAILURE: FailureSeverity.HIGH,
    FailureCategory.COMPACTION_FAILURE: FailureSeverity.HIGH,
    FailureCategory.ANSWER_GENERATION_FAILURE: FailureSeverity.MEDIUM,
    FailureCategory.JUDGE_FAILURE: FailureSeverity.LOW,
    FailureCategory.DATASET_ISSUE: FailureSeverity.HIGH,
    FailureCategory.SKIPPED: FailureSeverity.LOW,
    FailureCategory.UNKNOWN: FailureSeverity.MEDIUM,
}

ACTION_BY_CATEGORY = {
    FailureCategory.RETRIEVAL_FAILURE: (
        "Inspect retrieval recall, query normalization, and candidate generation."
    ),
    FailureCategory.RANKING_FAILURE: (
        "Inspect ranking features and why retrieved evidence was not selected."
    ),
    FailureCategory.CONTEXT_BUDGET_FAILURE: (
        "Inspect context budget allocation and evidence retention priorities."
    ),
    FailureCategory.LIFECYCLE_FILTER_FAILURE: (
        "Inspect lifecycle state assignment and filtering decisions."
    ),
    FailureCategory.SESSION_CONTINUITY_FAILURE: (
        "Inspect session identity propagation and session-aware retrieval."
    ),
    FailureCategory.CONFLICT_RESOLUTION_FAILURE: (
        "Inspect conflict groups, supersession state, and stale-memory suppression."
    ),
    FailureCategory.COMPACTION_FAILURE: (
        "Inspect compaction retention criteria for important evidence."
    ),
    FailureCategory.ANSWER_GENERATION_FAILURE: (
        "Inspect answer generation using the already-correct retrieved context."
    ),
    FailureCategory.JUDGE_FAILURE: (
        "Inspect judge configuration, output validation, and preserved raw response."
    ),
    FailureCategory.DATASET_ISSUE: (
        "Inspect the source annotation without modifying official benchmark labels."
    ),
    FailureCategory.SKIPPED: "Install or enable the skipped optional capability.",
    FailureCategory.UNKNOWN: (
        "Collect additional trace or result evidence before assigning a root cause."
    ),
}


class FailureClassifier:
    """Classify observed failures without inferring beyond available evidence."""

    def classify_case(
        self,
        benchmark: str,
        case_id: str,
        provider: str,
        query: str,
        expected_ids: list[str],
        forbidden_ids: list[str],
        retrieved_ids: list[str],
        included_ids: list[str],
        excluded_ids: list[str],
        trace_ids: list[str],
        trace_summaries: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[FailureCase]:
        details = metadata or {}
        traces = trace_summaries or []
        signals = _merge_trace_signals(traces)
        expected = set(expected_ids)
        forbidden = set(forbidden_ids)
        retrieved = set(retrieved_ids)
        included = set(included_ids)
        excluded = set(excluded_ids)
        failures: list[FailureCase] = []

        status = str(details.get("status", "")).lower()
        if status == "skipped":
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.SKIPPED,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    str(
                        details.get("skip_reason") or "Provider execution was skipped."
                    ),
                    ["status=skipped"],
                    details,
                )
            )
            return failures

        dataset_evidence = _dataset_issue_evidence(details, expected_ids)
        if dataset_evidence:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.DATASET_ISSUE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "Dataset evidence is missing, malformed, or references unavailable IDs.",
                    dataset_evidence,
                    details,
                )
            )

        missing = sorted(expected - retrieved - included)
        if missing:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.RETRIEVAL_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    f"Expected evidence was absent from retrieval and context: {', '.join(missing)}.",
                    [f"missing_expected_ids={','.join(missing)}"],
                    details,
                )
            )

        context_available = bool(
            details.get("context_available", included_ids or excluded_ids)
        )
        not_included = (
            sorted(expected & retrieved - included) if context_available else []
        )
        low_ranked = _low_ranked_expected(expected, details)
        ranking_evidence = sorted(set(not_included + low_ranked))
        if ranking_evidence:
            evidence = []
            if not_included:
                evidence.append(f"retrieved_not_included_ids={','.join(not_included)}")
            if low_ranked:
                evidence.append(f"low_ranked_expected_ids={','.join(low_ranked)}")
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.RANKING_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "Expected evidence was retrieved but ranked outside the usable context selection.",
                    evidence,
                    details,
                )
            )

        budget_ids = sorted(
            expected & retrieved & set(signals["budget_excluded_ids"]) - included
        )
        affected = (
            budget_ids or sorted(expected & excluded - included) or not_included
            if signals["budget_exhausted"] and context_available
            else []
        )
        if affected:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.CONTEXT_BUDGET_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "Expected evidence was retrieved but excluded when the context budget was exhausted.",
                    [
                        f"budget_excluded_ids={','.join(affected)}",
                        "trace_budget_exhausted=true",
                    ],
                    details,
                )
            )

        lifecycle_ids = sorted(
            expected & set(signals["lifecycle_excluded_ids"]) - included
        )
        if (
            signals["lifecycle_penalty"] or signals["archived_or_superseded_filtering"]
        ) and not lifecycle_ids:
            lifecycle_ids = sorted(expected & excluded - included)
        if lifecycle_ids:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.LIFECYCLE_FILTER_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "Expected evidence was excluded by an archived, superseded, inactive, or penalized lifecycle decision.",
                    [f"lifecycle_excluded_ids={','.join(lifecycle_ids)}"],
                    details,
                )
            )

        session_ids = _missing_current_session_ids(
            expected, retrieved | included, details
        )
        if session_ids:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.SESSION_CONTINUITY_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "Expected memories from the current session were not retrieved or included.",
                    [
                        f"current_session_id={details.get('current_session_id')}",
                        f"missing_current_session_ids={','.join(session_ids)}",
                    ],
                    details,
                )
            )

        forbidden_used = sorted(forbidden & (retrieved | included))
        if forbidden_used:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.CONFLICT_RESOLUTION_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "Forbidden stale, superseded, or conflicting memory was retrieved or included.",
                    [f"used_forbidden_ids={','.join(forbidden_used)}"],
                    details,
                )
            )

        compacted_ids = _compacted_ids(details)
        if compacted_ids is not None:
            compaction_missing = sorted(expected - set(compacted_ids))
            if compaction_missing:
                failures.append(
                    self._failure(
                        benchmark,
                        case_id,
                        provider,
                        query,
                        FailureCategory.COMPACTION_FAILURE,
                        expected_ids,
                        retrieved_ids,
                        included_ids,
                        excluded_ids,
                        forbidden_ids,
                        trace_ids,
                        "Expected evidence was not retained by available compaction output.",
                        [
                            f"missing_after_compaction_ids={','.join(compaction_missing)}"
                        ],
                        details,
                    )
                )

        usable_context = included if context_available else retrieved
        if _answer_failed(details) and expected <= usable_context:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.ANSWER_GENERATION_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "Required evidence reached the usable context, but deterministic answer metrics failed.",
                    _answer_evidence(details),
                    details,
                )
            )

        judge_evidence = _judge_failure_evidence(details)
        if judge_evidence:
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.JUDGE_FAILURE,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "The optional judge was requested but skipped, errored, or returned invalid output.",
                    judge_evidence,
                    details,
                )
            )

        if not failures and _failure_observed(details):
            failures.append(
                self._failure(
                    benchmark,
                    case_id,
                    provider,
                    query,
                    FailureCategory.UNKNOWN,
                    expected_ids,
                    retrieved_ids,
                    included_ids,
                    excluded_ids,
                    forbidden_ids,
                    trace_ids,
                    "A failure was observed, but available result and trace evidence do not support a specific root cause.",
                    ["insufficient_root_cause_evidence=true"],
                    details,
                )
            )
        return failures

    def _failure(
        self,
        benchmark: str,
        case_id: str,
        provider: str,
        query: str,
        category: FailureCategory,
        expected_ids: list[str],
        retrieved_ids: list[str],
        included_ids: list[str],
        excluded_ids: list[str],
        forbidden_ids: list[str],
        trace_ids: list[str],
        reason: str,
        evidence: list[str],
        metadata: dict[str, Any],
    ) -> FailureCase:
        return FailureCase(
            id=f"{benchmark}:{case_id}:{provider}:{category.value}",
            benchmark=benchmark,
            case_id=case_id,
            provider=provider,
            category=category,
            severity=SEVERITY_BY_CATEGORY[category],
            query=query,
            expected_ids=_unique(expected_ids),
            retrieved_ids=_unique(retrieved_ids),
            included_ids=_unique(included_ids),
            excluded_ids=_unique(excluded_ids),
            forbidden_ids=_unique(forbidden_ids),
            trace_ids=_unique(trace_ids),
            reason=reason,
            evidence=evidence,
            suggested_action=_suggested_action(provider, category),
            expected_behavior=_expected_baseline_behavior(provider, category),
            interpretation=_provider_interpretation(provider, category),
            metadata=_failure_metadata(metadata),
        )


def analyze_trace_for_failure_signals(trace_export: Any) -> dict[str, Any]:
    """Extract stable trace signals while tolerating unknown export structures."""

    signals: dict[str, Any] = {
        "budget_exhausted": False,
        "excluded_memory_ids": [],
        "budget_excluded_ids": [],
        "lifecycle_penalty": False,
        "lifecycle_excluded_ids": [],
        "archived_or_superseded_filtering": False,
        "session_boost_used": False,
        "session_boost_skipped": False,
        "conflict_event": False,
        "compaction_decision": False,
        "reranker_used": False,
        "semantic_retrieval_used": False,
        "access_count_updated": False,
    }
    for event in _events(trace_export):
        event_type = _event_type(event)
        data = _event_data(event)
        memory_id = _memory_id(event, data)
        reason = _structured_reason(event, data)
        status = _structured_value(event, data, "status", "lifecycle_status")
        decision = _structured_value(event, data, "decision", "action")
        stable = " ".join((event_type, reason, status, decision)).lower()

        if _matches(stable, "budget_exhausted", "token_budget_exhausted") or (
            "budget" in stable and _matches(stable, "exclude", "exhaust", "limit")
        ):
            signals["budget_exhausted"] = True
            if memory_id:
                signals["budget_excluded_ids"].append(memory_id)
        if _matches(event_type, "memory_excluded", "excluded", "suppressed"):
            if memory_id:
                signals["excluded_memory_ids"].append(memory_id)
        if _matches(stable, "lifecycle_penalty", "lifecycle_filter"):
            signals["lifecycle_penalty"] = True
        if _matches(stable, "archived", "superseded", "inactive"):
            signals["archived_or_superseded_filtering"] = True
            if memory_id and _matches(
                stable, "exclude", "filter", "suppress", "reject"
            ):
                signals["lifecycle_excluded_ids"].append(memory_id)
        if "session" in stable and "boost" in stable:
            if _matches(stable, "skip", "disabled", "not_used"):
                signals["session_boost_skipped"] = True
            else:
                signals["session_boost_used"] = True
        if _matches(event_type, "conflict", "contradiction", "supersed"):
            signals["conflict_event"] = True
        if "compaction" in event_type or "compaction" in stable:
            signals["compaction_decision"] = True
        if "rerank" in event_type or "rerank" in stable:
            signals["reranker_used"] = True
        if "semantic" in event_type and "retriev" in stable:
            signals["semantic_retrieval_used"] = True
        if "access_count" in stable and _matches(stable, "update", "increment"):
            signals["access_count_updated"] = True
    for key in (
        "excluded_memory_ids",
        "budget_excluded_ids",
        "lifecycle_excluded_ids",
    ):
        signals[key] = _unique(signals[key])
    return signals


def _merge_trace_signals(traces: list[dict[str, Any]]) -> dict[str, Any]:
    merged = analyze_trace_for_failure_signals({})
    for trace in traces:
        signals = analyze_trace_for_failure_signals(trace)
        for key, value in signals.items():
            if isinstance(value, bool):
                merged[key] = bool(merged[key] or value)
            elif isinstance(value, list):
                merged[key] = _unique([*merged[key], *value])
    return merged


def _events(trace_export: Any) -> list[Mapping[str, Any]]:
    events: list[Mapping[str, Any]] = []
    _collect_events(trace_export, events)
    return events


def _collect_events(value: Any, events: list[Mapping[str, Any]]) -> None:
    if isinstance(value, Mapping):
        if any(key in value for key in ("event_type", "type", "name")):
            events.append(value)
        for key in ("trace", "events", "decisions", "operations", "children", "data"):
            nested = value.get(key)
            if nested is not None and nested is not value:
                _collect_events(nested, events)
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for item in value:
            _collect_events(item, events)


def _event_type(event: Mapping[str, Any]) -> str:
    return str(
        event.get("event_type") or event.get("type") or event.get("name") or ""
    ).lower()


def _event_data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("data")
    return value if isinstance(value, Mapping) else {}


def _memory_id(event: Mapping[str, Any], data: Mapping[str, Any]) -> str | None:
    value = _structured_value(
        event, data, "dataset_memory_id", "memory_id", "dialog_id", "id"
    )
    return value or None


def _structured_reason(event: Mapping[str, Any], data: Mapping[str, Any]) -> str:
    return _structured_value(event, data, "reason", "reason_code", "explanation")


def _structured_value(
    event: Mapping[str, Any], data: Mapping[str, Any], *keys: str
) -> str:
    for source in (event, data):
        for key in keys:
            value = source.get(key)
            if value is not None:
                return str(value)
    return ""


def _matches(value: str, *terms: str) -> bool:
    return any(term in value for term in terms)


def _low_ranked_expected(expected: set[str], metadata: dict[str, Any]) -> list[str]:
    ranks = metadata.get("retrieval_ranks") or metadata.get("rank_by_id")
    cutoff = metadata.get("rank_cutoff") or metadata.get("context_limit")
    if not isinstance(ranks, Mapping) or not isinstance(cutoff, int):
        return []
    return sorted(
        memory_id
        for memory_id in expected
        if isinstance(ranks.get(memory_id), int) and ranks[memory_id] > cutoff
    )


def _missing_current_session_ids(
    expected: set[str], available: set[str], metadata: dict[str, Any]
) -> list[str]:
    current = metadata.get("current_session_id")
    sessions = metadata.get("memory_sessions")
    if current is None or not isinstance(sessions, Mapping):
        return []
    current_expected = {
        memory_id
        for memory_id in expected
        if str(sessions.get(memory_id, "")) == str(current)
    }
    return sorted(current_expected - available)


def _compacted_ids(metadata: dict[str, Any]) -> list[str] | None:
    if metadata.get("compaction_available") is False:
        return None
    for key in ("compacted_ids", "compacted_memory_ids", "retained_memory_ids"):
        value = metadata.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    return None


def _answer_failed(metadata: dict[str, Any]) -> bool:
    if metadata.get("answer_metric_failed") is True:
        return True
    metrics = metadata.get("answer_metrics")
    if not isinstance(metrics, Mapping):
        return False
    for key in ("diagnostic_score", "exact_match", "token_f1"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            return float(value) <= 0.0
    return False


def _answer_evidence(metadata: dict[str, Any]) -> list[str]:
    metrics = metadata.get("answer_metrics")
    if not isinstance(metrics, Mapping):
        return ["answer_metric_failed=true"]
    return [
        f"{key}={value}"
        for key, value in sorted(metrics.items())
        if isinstance(value, (int, float))
    ] or ["answer_metric_failed=true"]


def _judge_failure_evidence(metadata: dict[str, Any]) -> list[str]:
    judge = metadata.get("judge_result")
    if not isinstance(judge, Mapping):
        return []
    status = str(judge.get("status", "")).lower()
    requested = metadata.get("judge_requested") is True
    if status not in {"error", "invalid", "skipped"} or (
        status == "skipped" and not requested
    ):
        return []
    evidence = [f"judge_status={status}"]
    if judge.get("reason"):
        evidence.append(f"judge_reason={judge['reason']}")
    return evidence


def _dataset_issue_evidence(
    metadata: dict[str, Any], expected_ids: list[str]
) -> list[str]:
    evidence: list[str] = []
    warnings = metadata.get("dataset_warnings")
    if isinstance(warnings, list) and warnings:
        evidence.append(f"dataset_warning_count={len(warnings)}")
    if metadata.get("dataset_issue"):
        evidence.append(f"dataset_issue={metadata['dataset_issue']}")
    if metadata.get("evidence_required") is True and not expected_ids:
        evidence.append("required_evidence_ids_missing=true")
    return evidence


def _failure_observed(metadata: dict[str, Any]) -> bool:
    return bool(
        metadata.get("failure_observed")
        or metadata.get("case_failed")
        or str(metadata.get("status", "")).lower() == "failed"
    )


def _failure_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "benchmark_category",
        "current_session_id",
        "evaluation_mode",
        "conversation_id",
        "status",
    )
    return {key: metadata[key] for key in keys if key in metadata}


def _unique(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value is not None))


def _suggested_action(provider: str, category: FailureCategory) -> str:
    action = ACTION_BY_CATEGORY[category]
    if provider == "mneno":
        return f"Mneno Core: {action}"
    if is_baseline_provider(provider):
        note = _provider_interpretation(provider, category)
        return f"Comparison evidence: {note or action}"
    return action


def _expected_baseline_behavior(provider: str, category: FailureCategory) -> bool:
    if provider == "full_context_baseline":
        return category == FailureCategory.CONFLICT_RESOLUTION_FAILURE
    if provider == "random_baseline":
        return category == FailureCategory.RETRIEVAL_FAILURE
    if provider == "keyword_baseline":
        return category in {
            FailureCategory.RETRIEVAL_FAILURE,
            FailureCategory.SESSION_CONTINUITY_FAILURE,
        }
    return False


def _provider_interpretation(provider: str, category: FailureCategory) -> str | None:
    if provider == "full_context_baseline":
        if category == FailureCategory.CONFLICT_RESOLUTION_FAILURE:
            return (
                "Full Context intentionally includes all memories, so stale or "
                "forbidden-memory use is expected comparison behavior, not by itself "
                "a product bug."
            )
        return (
            "Full Context failures quantify the risk and cost of including everything."
        )
    if provider == "random_baseline":
        return (
            "Random retrieval failures are expected baseline behavior and provide a "
            "lower-bound comparison."
        )
    if provider == "keyword_baseline":
        return (
            "Keyword retrieval and session failures reflect known lexical and "
            "session-awareness limitations of this comparison baseline."
        )
    if provider == "mneno":
        return "This failure is evidence for investigating Mneno Core behavior."
    return None
