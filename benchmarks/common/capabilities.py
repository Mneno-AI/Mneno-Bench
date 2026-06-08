"""Capability discovery for optional Mneno Core versions."""

from __future__ import annotations

from typing import Any, Protocol

from benchmarks.common.schema import MnenoCapabilityReport

MNENO_CAPABILITIES = (
    "add_with_report",
    "evaluate_search",
    "evaluate_context",
    "evaluate_compaction",
    "build_context",
    "create_session",
    "evaluate_hierarchy",
    "preview_compaction",
    "export_trace",
    "export_all_traces",
)


class CapabilityAdapter(Protocol):
    def is_available(self) -> bool: ...

    def version(self) -> str | None: ...

    def supports(self, name: str, client: Any | None = None) -> bool: ...


def detect_mneno_capabilities(
    adapter: CapabilityAdapter, client: Any | None = None
) -> MnenoCapabilityReport:
    """Return a stable serializable report without invoking optional methods."""

    available = adapter.is_available()
    if not available:
        return MnenoCapabilityReport(
            available=False,
            capabilities={name: False for name in MNENO_CAPABILITIES},
            missing=list(MNENO_CAPABILITIES),
            partial=False,
        )
    capabilities = {
        name: adapter.supports(name, client=client) for name in MNENO_CAPABILITIES
    }
    missing = [name for name, supported in capabilities.items() if not supported]
    return MnenoCapabilityReport(
        available=True,
        version=adapter.version(),
        capabilities=capabilities,
        missing=missing,
        partial=bool(missing),
    )
