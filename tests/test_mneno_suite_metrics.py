from benchmarks.common.schema import MnenoDecisionSummary, TraceSummary
from benchmarks.mneno_suite.dataset import MnenoSuiteMemory
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


def _memories() -> dict[str, MnenoSuiteMemory]:
    return {
        "active": MnenoSuiteMemory(
            id="active",
            content="active expected fact",
            memory_type="fact",
            status="active",
            importance=1.0,
            session_id="current",
        ),
        "stale": MnenoSuiteMemory(
            id="stale",
            content="stale forbidden fact",
            memory_type="fact",
            status="superseded",
            importance=0.5,
            session_id="old",
        ),
        "noise": MnenoSuiteMemory(
            id="noise",
            content="unrelated noisy fact with several extra words",
            memory_type="note",
            status="active",
            importance=0.1,
            session_id="old",
        ),
    }


def test_recall_suppression_and_forbidden_error() -> None:
    assert expected_memory_recall(["active"], ["active", "other"]) == 0.5
    assert stale_memory_suppression_rate(["active"], ["stale"]) == 1.0
    assert forbidden_memory_error_rate(["active", "stale"], ["stale"]) == 1.0


def test_context_efficiency_rewards_only_useful_tokens() -> None:
    memories = _memories()
    perfect = context_efficiency_score(["active"], ["active"], memories)
    noisy = context_efficiency_score(["active", "noise"], ["active"], memories)

    assert perfect == 1.0
    assert 0.0 < noisy < perfect


def test_lifecycle_and_session_alignment() -> None:
    memories = _memories()
    assert lifecycle_alignment_score(["active"], ["active"], ["stale"], memories) == 1.0
    assert lifecycle_alignment_score(["stale"], ["active"], ["stale"], memories) == 0.0
    assert (
        session_continuity_score(["active"], ["active"], ["stale"], memories, "current")
        == 1.0
    )


def test_compaction_retention_and_explainability() -> None:
    memories = _memories()
    assert compaction_retention_score(["active"], ["active"], memories) == 1.0
    assert compaction_retention_score([], ["active"], memories) == 0.0
    trace = TraceSummary(decision_count=1, event_count=1)
    assert explainability_coverage_score(["active", "stale"], trace) == 1.0
    decisions = MnenoDecisionSummary(inclusion_reasons={"active": ["current session"]})
    assert explainability_coverage_score(["active"], None, decisions) == 1.0
    assert explainability_coverage_score(["active"], None) == 0.0
