"""Small deterministic retrieval baselines for early Mneno validation."""

from __future__ import annotations

import hashlib
import random
import re
from time import perf_counter
from typing import Any

from benchmarks.common.schema import NormalizedSearchResult


def _memory_id(memory: dict[str, Any]) -> str:
    return str(memory["id"])


def _terms(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _memory_text(memory: dict[str, Any]) -> str:
    return str(memory.get("content", memory.get("text", "")))


def random_baseline(
    memories: list[dict[str, Any]], query: str, k: int = 3
) -> NormalizedSearchResult:
    """Return a query-seeded deterministic random sample."""

    seed = int(hashlib.sha256(query.encode("utf-8")).hexdigest()[:16], 16)
    shuffled = list(memories)
    random.Random(seed).shuffle(shuffled)
    started = perf_counter()
    memory_ids = [_memory_id(memory) for memory in shuffled[:k]]
    return _normalized("random", query, memory_ids, started)


def keyword_baseline(
    memories: list[dict[str, Any]], query: str, k: int = 3
) -> NormalizedSearchResult:
    """Rank memories by token overlap, then by stable input order."""

    started = perf_counter()
    query_terms = _terms(query)
    scored = [
        (
            len(query_terms & _terms(_memory_text(memory))),
            index,
            _memory_id(memory),
        )
        for index, memory in enumerate(memories)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    memory_ids = [memory_id for _, _, memory_id in scored[:k]]
    return _normalized("keyword", query, memory_ids, started)


def full_context_baseline(
    memories: list[dict[str, Any]], query: str, k: int | None = None
) -> NormalizedSearchResult:
    """Return every memory in source order as the no-compaction baseline."""

    del k
    started = perf_counter()
    memory_ids = [_memory_id(memory) for memory in memories]
    return _normalized("full_context", query, memory_ids, started)


def _normalized(
    provider: str, query: str, memory_ids: list[str], started: float
) -> NormalizedSearchResult:
    return NormalizedSearchResult(
        provider=provider,
        query=query,
        metrics={"latency_ms": round((perf_counter() - started) * 1000, 4)},
        raw_result={"retrieved_memory_ids": memory_ids},
    )
