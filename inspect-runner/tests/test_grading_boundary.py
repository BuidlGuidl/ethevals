"""Classify the cause of a failure through exported rows."""
import pytest

from test_contracts import scoring_case, YES
from ethevals.scorers import prepare_forge, forge as real_forge


@pytest.mark.parametrize("operation", ["stop_agent", "workspace_files"])
@pytest.mark.parametrize("error", [ValueError("Docker exec failed"), TimeoutError("Docker exec timed out")])
def test_capture_transport_failure_is_an_error(scoring_case, monkeypatch, operation, error):
    async def broken():
        raise error
    monkeypatch.setattr("ethevals.scorers." + operation, broken)
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"], row["attempt"]) == ("error", None, 1)
    assert all(not check["passed"] for check in row["checks"].values())


def test_empty_grader_reason_fails_the_rubric_check(scoring_case):
    row = scoring_case["run"](['{"passed": true, "reason": " "}', YES])
    assert (row["status"], row["passed"]) == ("failed", False)
    assert row["checks"]["rubric:uses_openzeppelin"] == {
        "passed": False, "reason": "The grader could not justify a verdict."}
    assert row["checks"]["rubric:protects_holders"]["passed"] is True


def test_docker_timeout_during_oom_inspection_is_an_error(scoring_case, monkeypatch):
    from types import SimpleNamespace
    from inspect_ai.util import ExecResult
    from inspect_ai.util._sandbox.docker.docker import DockerSandboxEnvironment

    box = object.__new__(DockerSandboxEnvironment)
    box._project = SimpleNamespace(name="test")
    box._service = "scorer"

    async def killed(*args, **kwargs):
        return ExecResult(success=False, returncode=137, stdout="", stderr="")

    async def unavailable(*args, **kwargs):
        raise TimeoutError("Docker inspect timed out")

    monkeypatch.setattr("ethevals.scorers.sandbox", lambda name: box)
    monkeypatch.setattr("ethevals.scorers.forge", real_forge)
    monkeypatch.setattr("ethevals.sandboxes.runner_exec", killed)
    monkeypatch.setattr("ethevals.sandboxes.anyio.run_process", unavailable)
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"]) == ("error", None)
    assert "Cannot inspect scorer memory state" in row["error_reason"]


def test_invalid_source_bytes_fail_all_checks(scoring_case, monkeypatch):
    from inspect_ai.util import ExecResult

    class Box:
        async def exec(self, *args, **kwargs):
            return ExecResult(success=True, returncode=0, stdout="", stderr="")

    scoring_case["source"] = {"src/Token.sol": b"pragma solidity =0.8.30; //\xff\ncontract Token {}"}
    monkeypatch.setattr("ethevals.scorers.sandbox", lambda name: Box())
    monkeypatch.setattr("ethevals.scorers.prepare_forge", prepare_forge)
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"]) == ("failed", False)
    assert set(check["reason"] for check in row["checks"].values()) == {"Solidity source is not valid UTF-8: src/Token.sol"}


@pytest.mark.parametrize("timeout", [False, True])
def test_chain_capture_failure_is_an_error(tmp_path, monkeypatch, timeout):
    from dataclasses import replace
    from inspect_ai import eval
    from inspect_ai.util import ExecResult
    from ethevals.config import load_config
    from ethevals.loader import load_eval
    from ethevals.checks import check_player, check_grader
    from ethevals.runner import build_task
    from ethevals.rows import results_rows
    from test_ci import ROOT

    config = load_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    evaluation = replace(evaluation, discovered_checks={"check_script": ("script:balance",)})
    task = build_task(evaluation, config, check_player(evaluation, "empty"), check_grader(), "internet", 1)
    task.dataset[0].sandbox = task.dataset[0].files = None

    async def stopped():
        pass

    async def failed(*args, **kwargs):
        if timeout:
            raise TimeoutError("Docker freeze timed out")
        return ExecResult(success=False, returncode=1, stdout="", stderr="Docker exec failed")

    monkeypatch.setattr("ethevals.scorers.stop_agent", stopped)
    monkeypatch.setattr("ethevals.check_script.sandbox", lambda name: object())
    monkeypatch.setattr("ethevals.check_script.runner_exec", failed)
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    assert (row["status"], row["passed"]) == ("error", None)
    assert row["checks"]["script:balance"]["passed"] is False
