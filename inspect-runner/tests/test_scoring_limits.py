"""Scoring limits and failure rows through Inspect."""
import json
from pathlib import Path

import pytest
from inspect_ai import eval
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.solver import solver

from support import fixture_config
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from ethevals.scorers import forge_checks
from support import build_task
from test_contracts import scoring_case, YES, BUILD

CAPTURES = json.loads((Path(__file__).parent / "fixtures/forge-1.5.1.json").read_text())


def test_captured_constructor_failure_keeps_forge_check_name():
    assert forge_checks(**CAPTURES["constructor"]) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        "forge:test/Token.t.sol:Tests:constructor()": {"passed": False, "reason": "bad submission"},
    }


@pytest.mark.parametrize("code,stdout,stderr,reason", [
    (1, "", "thread panicked", "without test results"),
    (1, '{"truncated":', "Error: Compilation failed", "without test results"),
    (137, CAPTURES["reference"]["stdout"], "", "terminated"),
])
def test_unexplained_forge_failure_is_an_error(code, stdout, stderr, reason):
    with pytest.raises(RuntimeError, match=reason):
        forge_checks(stdout, stderr, code)


@pytest.mark.docker
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
    row = scoring_case["run"](replies)
    assert row["status"] == "error"
    assert "Grader exceeded its total call deadline" in row["error_reason"]
    assert (scoring_case["log"].samples[0].role_usage["grader"].total_tokens if "grader" in scoring_case["log"].samples[0].role_usage else 0) == 0


def test_build_rejects_scoring_window_that_cannot_fit():
    config = fixture_config()
    evaluation = load_eval(BUILD, config)
    config.time_limits["build"] = 300
    with pytest.raises(ValueError, match="Scoring needs 540 seconds, but Inspect allows 450"):
        build_task(evaluation, config, None, "internet", "reference", 1)


@pytest.mark.docker
def test_operator_stop_is_an_error_and_skips_scoring(scoring_case):
    from inspect_ai._util.exception import TerminateSampleError

    @solver
    def stopped():
        async def solve(state, generate):
            raise TerminateSampleError("Stopped by operator")
        return solve

    scoring_case["task"].solver = stopped()
    row = scoring_case["run"]([])
    assert (row["status"], row["limit"]["type"]) == ("error", "operator")
    assert "Stopped by operator" in row["error_reason"]


@pytest.mark.docker
def test_wall_backstop_is_an_error(scoring_case):
    from support import mock_delay
    scoring_case["task"].solver = mock_delay(2)
    scoring_case["task"].time_limit = 1
    row = scoring_case["run"]([])
    assert (row["status"], row["limit"]["type"]) == ("error", "time")
    assert row["working_seconds"] < scoring_case["log"].eval.metadata["working_limit_seconds"]


def test_provider_backoff_does_not_spend_working_limit(tmp_path, monkeypatch):
    import httpx
    from inspect_ai.model._providers.mockllm import MockLLM
    from tenacity import wait_fixed
    config = fixture_config()
    config.time_limits["quiz"] = 1
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
    assert (row["status"], attempts) == ("passed", 2)
    assert row["total_seconds"] >= 1.5
    assert row["working_seconds"] < 1
