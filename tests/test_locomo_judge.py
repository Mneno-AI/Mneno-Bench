from typing import Any

from benchmarks.common.llm_client import LLMConfig
from benchmarks.locomo.answering import AnswerCandidate
from benchmarks.locomo.judge import LOCOMOJudge


class FakeLLMClient:
    def __init__(self, response: str | Exception) -> None:
        self.config = LLMConfig(model="fake-model", provider="fake-provider")
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str, **overrides: Any) -> str:
        del overrides
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _candidate() -> AnswerCandidate:
    return AnswerCandidate(
        provider="keyword_baseline",
        question_id="q1",
        answer="Rome",
        context="Alex moved to Rome.",
    )


def test_judge_parses_valid_json_response() -> None:
    client = FakeLLMClient('{"correct": true, "score": 1, "reason": "match"}')
    judge = LOCOMOJudge(client)

    result = judge.evaluate("Where did Alex move?", "Rome", _candidate())

    assert result.status == "completed"
    assert result.correct is True
    assert result.score == 1.0
    assert result.model == "fake-model"
    assert client.prompts


def test_judge_invalid_json_marks_error() -> None:
    result = LOCOMOJudge(FakeLLMClient("not json")).evaluate(
        "Where did Alex move?", "Rome", _candidate()
    )

    assert result.status == "error"
    assert result.score is None
    assert "Invalid judge JSON" in result.reason


def test_judge_rejects_invalid_json_types() -> None:
    result = LOCOMOJudge(
        FakeLLMClient('{"correct": "false", "score": 2, "reason": "invalid"}')
    ).evaluate("Where did Alex move?", "Rome", _candidate())

    assert result.status == "error"
    assert result.score is None


def test_judge_missing_api_key_runtime_error_is_skipped() -> None:
    result = LOCOMOJudge(
        FakeLLMClient(RuntimeError("External calls disabled"))
    ).evaluate("Where did Alex move?", "Rome", _candidate())

    assert result.status == "skipped"
    assert result.reason == "External calls disabled"
