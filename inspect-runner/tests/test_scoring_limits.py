"""Scoring limits and failure rows through Inspect."""
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from inspect_ai import eval
from inspect_ai.event import ModelEvent
from inspect_ai.model import ChatMessageUser, ChatMessageTool, ModelOutput, get_model
from inspect_ai.solver import solver

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from ethevals.scorers import forge_checks
from ethevals.search import valid_search_result
from support import build_task
from test_contracts import scoring_case, YES, BUILD

CAPTURES = json.loads((Path(__file__).parent / "fixtures/forge-1.5.1.json").read_text())
CHECK = "forge:test/Token.t.sol:Tests:testToken()"


def test_captured_constructor_failure_fills_suite_checks():
    assert forge_checks(**CAPTURES["constructor"], expected=[CHECK]) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        CHECK: {"passed": False, "reason": "bad submission"},
    }


@pytest.mark.parametrize("code,stdout,stderr,reason", [
    (1, "", "thread panicked", "without test results"),
    (1, '{"truncated":', "Error: Compilation failed", "without test results"),
    (137, CAPTURES["reference"]["stdout"], "", "terminated"),
])
def test_unexplained_forge_failure_is_an_error(code, stdout, stderr, reason):
    with pytest.raises(RuntimeError, match=reason):
        forge_checks(stdout, stderr, code, [CHECK])


def test_unexplained_forge_failure_produces_error_row(scoring_case):
    scoring_case.update(stdout="", stderr="Forge panicked", returncode=1)
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"]) == ("error", None)
    assert "without test results or a compiler diagnostic" in row["error_reason"]


@pytest.mark.parametrize("case,reason", [
    ("constructor", "forge:test/Token.t.sol:Tests:constructor(): bad submission"),
    ("syntax", "Error (6933): Expected primary expression."),
])
def test_discovery_error_names_failure(scoring_case, monkeypatch, case, reason):
    import ethevals.preparation as preparation
    scoring_case.update(CAPTURES[case])
    task = scoring_case["task"]
    task.scorer = [preparation.reference_checks(task.metadata["eval_id"], task.metadata["eval_hash"])]
    row = scoring_case["run"]([])
    assert row["status"] == "error"
    assert reason in row["error_reason"]
    assert "uint x" not in row["error_reason"]


def test_grader_effective_config_and_recorded_ceiling(scoring_case):
    row = scoring_case["run"]([YES, YES])
    assert row["status"] == "passed"
    assert row["grader_cost_limit_usd"] == pytest.approx(23.7288)
    assert [(item.max_retries, item.timeout, item.attempt_timeout, item.max_tokens, item.reasoning_effort)
            for item in scoring_case["configs"]] == [(2, 60, 20, 4096, "none")] * 2
    assert (row["working_limit_seconds"], row["time_limit_seconds"], row["scoring_limit_seconds"]) == (1200, 3600, 540)


@pytest.mark.parametrize("waiting", ["provider", "backoff"])
def test_slow_provider_stops_at_total_grader_deadline(scoring_case, monkeypatch, waiting):
    import ethevals.scorers as scorers
    monkeypatch.setattr(scorers, "GRADER_CONFIG", scorers.GRADER_CONFIG.model_copy(update={"timeout": 1}))
    replies = [(5, YES)]
    if waiting == "backoff":
        import httpx
        from inspect_ai.model._providers.mockllm import MockLLM
        from tenacity import wait_fixed
        response = httpx.Response(503, request=httpx.Request("POST", "https://provider.invalid"))
        error = httpx.HTTPStatusError("Unavailable", request=response.request, response=response)
        replies = [error, YES]
        monkeypatch.setattr(MockLLM, "should_retry", lambda self, error: isinstance(error, httpx.HTTPStatusError))
        monkeypatch.setattr(MockLLM, "retry_wait", lambda self: wait_fixed(5))
    start = time.monotonic()
    row = scoring_case["run"](replies)
    elapsed = time.monotonic() - start
    assert row["status"] == "error"
    assert "Grader exceeded its total call deadline" in row["error_reason"]
    assert elapsed < 4
    assert row["grader_tokens"] == 0


def test_budget_reserves_timeout_attempts_and_invalid_replies(scoring_case, monkeypatch):
    import ethevals.scorers as scorers
    from inspect_ai.model._providers.mockllm import MockLLM
    from tenacity import wait_none
    monkeypatch.setattr(scorers, "GRADER_CONFIG", scorers.GRADER_CONFIG.model_copy(update={"attempt_timeout": 1}))
    monkeypatch.setattr(MockLLM, "retry_wait", lambda self: wait_none())
    replies = []
    for final in ["invalid", YES, "invalid", YES]:
        replies.extend([(2, YES), (2, YES), final])
    row = scoring_case["run"](replies)
    assert row["status"] == "passed"
    assert len(scoring_case["configs"]) == 12
    # All twelve requests can be billed, though Inspect meters only four.
    assert row["grader_tokens"] == 800
    assert row["grader_cost_limit_usd"] == pytest.approx(12 * 1.9774)


def test_non_ascii_evidence_fits_token_floor(scoring_case):
    from ethevals.scorers import grader_request_size
    source = ("//" + "\U0001f9ec\u0870" * 10000).encode()
    scoring_case["compiled"] = {f"src/Token{i}.sol": source for i in range(4)}
    row = scoring_case["run"]([YES, YES])
    assert row["status"] == "passed"
    for messages, config in zip(scoring_case["requests"], scoring_case["configs"]):
        evidence = json.loads(messages[1].text)
        assert evidence["files"]["src/Token0.sol"] == source.decode()
        assert evidence["omitted_file_count"] > 0
        assert messages[1].text.isascii()
        # A byte-fallback tokenizer is the worst case, one token per byte.
        byte_tokens = sum(len(message.text.encode()) for message in messages)
        assert byte_tokens <= grader_request_size(messages, config) <= 300000


def test_build_rejects_scoring_window_that_cannot_fit():
    config = load_config()
    evaluation = load_eval(BUILD, config)
    evaluation = replace(evaluation, declaration=evaluation.declaration.model_copy(update={"time_limit": 300}))
    with pytest.raises(ValueError, match="Scoring needs 540 seconds, but Inspect allows 450"):
        build_task(evaluation, config, None, "internet", "reference", 1)


def test_operator_stop_is_an_error_and_skips_scoring(scoring_case):
    from inspect_ai._util.exception import TerminateSampleError

    @solver
    def stopped():
        async def solve(state, generate):
            raise TerminateSampleError("Stopped by operator")
        return solve

    scoring_case["task"].solver = stopped()
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"], row["limit"]["type"]) == ("error", None, "operator")
    assert "Stopped by operator" in row["error_reason"]
    assert scoring_case["snapshots"] == 0


def test_wall_backstop_is_an_error(scoring_case):
    from ethevals.checks import mock_delay
    scoring_case["task"].solver = mock_delay(2)
    scoring_case["task"].time_limit = 1
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"], row["limit"]["type"]) == ("error", None, "time")
    assert row["working_seconds"] < row["working_limit_seconds"]
    assert scoring_case["snapshots"] == 0


def test_provider_backoff_does_not_spend_working_limit(tmp_path, monkeypatch):
    import httpx
    from inspect_ai.model._providers.mockllm import MockLLM
    from tenacity import wait_fixed
    config = load_config()
    config.time_limit = 1
    evaluation = load_eval(BUILD.parents[1] / "concepts/wei-per-ether", config)
    task = build_task(evaluation, config, None, "vanilla", "reference", 1)
    attempts = 0

    def reply(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            response = httpx.Response(429, request=httpx.Request("POST", "https://provider.invalid"))
            raise httpx.HTTPStatusError("rate limited", request=response.request, response=response)
        return ModelOutput.from_content("mockllm/model", "ANSWER: C")

    monkeypatch.setattr(MockLLM, "should_retry", lambda self, error: isinstance(error, httpx.HTTPStatusError))
    monkeypatch.setattr(MockLLM, "retry_wait", lambda self: wait_fixed(1.5))
    task.model = get_model("mockllm/model", custom_outputs=reply)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(log)[0]
    assert (row["status"], row["passed"], attempts) == ("passed", True, 2)
    assert row["total_seconds"] >= 1.5
    assert row["working_seconds"] < 1


@pytest.mark.parametrize("code_mode", [False, True])
def test_exa_rate_limit_in_transcript_counts_once(scoring_case, code_mode):
    from inspect_ai.log import read_eval_log, write_eval_log
    scoring_case["run"]([YES, YES])
    log = scoring_case["log"]
    function = "exec" if code_mode else "mcp__exa__web_search_exa"
    arguments = {"input": "text(await tools.mcp__exa__web_search_exa({query:'test'}));"} if code_mode else {"query": "test"}
    call = ModelOutput.for_tool_call("mockllm/model", function, arguments)
    result = json.dumps({"content": [{"type": "text", "text": "You've hit Exa's free MCP rate limit. See https://exa.ai"}]})
    message = ChatMessageTool(function=function, tool_call_id=call.message.tool_calls[0].id, content=result)
    messages = [ChatMessageUser(content="Search"), call.message, message]
    # Agent bridges keep tool results in repeated model inputs, without ToolEvents.
    event = ModelEvent(model="mockllm/model", input=messages, tools=[], tool_choice="none",
                       config={}, output=ModelOutput.from_content("mockllm/model", "Done"))
    log.samples[0].events.extend([event, event])
    write_eval_log(log, log.location)
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["status"], row["search_calls"], row["search_failed"], row["search_rate_limited"]) == ("passed", 1, 1, 1)
    assert valid_search_result(result) is False
    assert valid_search_result('Title: ERC-20\nURL: https://ethereum.org/erc20\nContent: Token standard') is True
