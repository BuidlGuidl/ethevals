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
    from inspect_ai.util import ExecResult
    box = object()

    async def killed(*args, **kwargs):
        if "/sys/fs/cgroup/memory.events" in args[1]:
            raise TimeoutError("Docker exec timed out")
        return ExecResult(success=False, returncode=137, stdout="", stderr="")

    monkeypatch.setattr("ethevals.scorers.sandbox", lambda name: box)
    monkeypatch.setattr("ethevals.scorers.forge", real_forge)
    monkeypatch.setattr("ethevals.sandboxes.runner_exec", killed)
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"]) == ("error", None)
    assert "Cannot inspect scorer memory state" in row["error_reason"]


@pytest.mark.parametrize("cause,status", [("wrapper", "error"), ("host_timeout", "error"),
    ("earlier_oom_wrapper", "error"), ("author125", "failed"),
    ("read_timeout", "error"), ("missing", "error"), ("crash", "failed"), ("json", "failed"),
    ("schema", "failed"), ("deadline", "failed"), ("output", "failed"), ("pass", "passed")])
def test_check_script_boundary_through_rows(tmp_path, monkeypatch, cause, status):
    from dataclasses import replace
    from inspect_ai import eval
    from inspect_ai.util import ExecResult
    from ethevals.config import load_config
    from ethevals.loader import load_eval
    from ethevals.checks import check_player, check_grader
    from ethevals.runner import build_task
    from ethevals.rows import results_rows
    from test_ci import ROOT

    class Box:
        async def exec(self, command, **kwargs):
            code, stdout = 0, ""
            if "/sys/fs/cgroup/memory.events" in command:
                stdout = "oom 5\noom_kill 5\n" if cause == "earlier_oom_wrapper" else "oom 0\noom_kill 0\n"
            elif "--freeze" in command:
                stdout = "{}"
            elif "/usr/bin/test" in command:
                code = 1 if cause == "missing" else 0
            elif "/usr/bin/timeout" in command:
                if cause == "host_timeout":
                    raise TimeoutError("Host compose exec timed out")
                code = {"wrapper": 125, "earlier_oom_wrapper": 125, "author125": 1, "crash": 1, "deadline": 124}.get(cause, 0)
            return ExecResult(success=code == 0, returncode=code, stdout=stdout, stderr="")

        async def read_file(self, path, **kwargs):
            if path == "/eval/script.status":
                return "125" if cause == "author125" else "1"
            if path != "/eval/script.stdout":
                return b""
            if cause == "read_timeout":
                raise TimeoutError("Host copy timed out")
            return {"json": b"not JSON", "schema": b"[]", "output": b"x" * 1048577}.get(
                cause, b'{"balance":{"passed":true,"reason":"Balance matches."}}')

    async def stopped():
        pass

    config = load_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    evaluation = replace(evaluation, discovered_checks={"check_script": ("script:balance",)})
    task = build_task(evaluation, config, check_player(evaluation, "empty"), check_grader(), "internet", 1)
    task.dataset[0].sandbox = task.dataset[0].files = None
    monkeypatch.setattr("ethevals.scorers.stop_agent", stopped)
    monkeypatch.setattr("ethevals.check_script.sandbox", lambda name: Box())
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    assert (row["status"], row["passed"]) == (status, None if status == "error" else status == "passed")
    assert list(row["checks"]) == ["script:balance"]


@pytest.mark.parametrize("counters,status", [("oom 1\noom_kill 1\n", "failed"),
                                             ("oom 0\noom_kill 1\n", "error")])
def test_compiler_child_exit_one_and_host_oom_through_rows(scoring_case, monkeypatch, counters, status):
    from inspect_ai.util import ExecResult

    class Box:
        reads = 0
        async def exec(self, command, **kwargs):
            if "/sys/fs/cgroup/memory.events" in command:
                self.reads += 1
                return ExecResult(success=True, returncode=0, stdout="oom 0\noom_kill 0\n" if self.reads == 1 else counters, stderr="")
            return ExecResult(success=False, returncode=1, stdout="", stderr="")

        async def read_file(self, path, **kwargs):
            return b"Error: solc exited with signal: 9 (SIGKILL)" if "stderr" in path else b""

    monkeypatch.setattr("ethevals.scorers.sandbox", lambda name: Box())
    monkeypatch.setattr("ethevals.scorers.forge", real_forge)
    row = scoring_case["run"]([])
    assert (row["status"], row["passed"]) == (status, False if status == "failed" else None)


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
