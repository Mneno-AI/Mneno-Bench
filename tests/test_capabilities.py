from typing import Any

from benchmarks.common.capabilities import MNENO_CAPABILITIES, detect_mneno_capabilities


class FakeAdapter:
    def __init__(self, supported: set[str], available: bool = True) -> None:
        self.supported = supported
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def version(self) -> str:
        return "0.4.0"

    def supports(self, name: str, client: Any | None = None) -> bool:
        del client
        return name in self.supported


def test_capabilities_detect_supported_and_missing_methods() -> None:
    report = detect_mneno_capabilities(
        FakeAdapter({"evaluate_search", "build_context"})
    )

    assert report.available
    assert report.version == "0.4.0"
    assert report.capabilities["evaluate_search"]
    assert report.capabilities["build_context"]
    assert "preview_compaction" in report.missing
    assert report.partial
    assert report.model_dump(mode="json")["capabilities"]["build_context"]


def test_capabilities_reports_missing_sdk() -> None:
    report = detect_mneno_capabilities(FakeAdapter(set(), available=False))

    assert not report.available
    assert report.missing == list(MNENO_CAPABILITIES)
    assert not report.partial
