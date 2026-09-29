from dataclasses import replace
from pathlib import Path
import itertools
import json
import os
import shutil
import signal
import subprocess
import sys
import time

from ethevals.actors import select_actors
from ethevals.checks import CHECK_SOLVERS, CheckRun, check_grader
from ethevals.files import content_hash
from ethevals.loader import load_eval
from ethevals.planning import plan
from ethevals.preparation import prepare_compose
from ethevals.rows import fold_rows, previous_rows, read_rows, results_rows, write_rows
from ethevals.runner import build_task as actor_task
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelCost, ModelInfo, ModelOutput, ModelUsage, get_model, set_model_info
from inspect_ai.scorer import accuracy, scorer
from inspect_ai.solver import solver
from inspect_ai.util import sandbox
import pytest
import yaml

from support import build_task, catalog_quiz, fixture_config, mock_delay, run
from test_forge_docker import containers


ROOT = Path(__file__).resolve().parents[2]


@scorer(metrics={"*": [accuracy()]})
def with_grader(underlying):

    async def score(state, target):
        await get_model(role="grader").generate("Grade this answer.")
        return await underlying(state, target)
    return score


@solver
def crash():
    async def solve(state, generate):
        raise RuntimeError("Harness crashed in the test.")
    return solve


BUILD = ROOT / "inspect-runner/tests/fixtures/building/erc20-points-token"
CHECK = "forge:test/Token.t.sol:TokenTest:testSupply()"
YES = '{"passed": true, "reason": "Uses standard transfers."}'
NO = '{"passed": false, "reason": "Owner can seize tokens."}'


@solver
def submit_source(source):
    async def solve(state, generate):
        await sandbox().write_file("/workspace/src/BuilderPoints.sol", source)
        return await generate(state)
    return solve


def test_rows_split_grader_usage_for_the_same_model(folder, tmp_path):
    config = fixture_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.metadata.update(cost_source="computed:test", grader_cost_source="computed:grader", prices={"input": 1, "output": 2})
    output = ModelOutput.from_content("mockllm/model", "8004")
    output.usage = ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14)
    grade = ModelOutput.from_content("mockllm/model", "yes")
    grade.usage = ModelUsage(input_tokens=7, output_tokens=3, total_tokens=10)
    set_model_info("mockllm/model", ModelInfo(cost=ModelCost(input=1, output=2, input_cache_read=0, input_cache_write=0)))
    task.model = get_model("mockllm/model", custom_outputs=[output])
    task.scorer = [with_grader(task.scorer[0])]
    log = eval(task, model_roles={"grader": get_model("mockllm/model", custom_outputs=[grade])},
               log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert row["total_tokens"] == 24
    assert row["model_cost_usd"] == pytest.approx(0.000018)
    assert row["grader_cost_usd"] == pytest.approx(0.000013)
    assert row["cost_source"] == "computed:test"
    assert log.eval.metadata["prices"] == {"input": 1, "output": 2}


def test_error_is_distinct_from_failed_answer(folder, tmp_path):
    config = fixture_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.solver = crash()
    log = eval(task, fail_on_error=False, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["status"], row["error_kind"]) == ("error", "execution")
    assert "Harness crashed in the test." in row["error_reason"]


def test_working_limit_is_a_failed_check(folder, tmp_path):
    config = fixture_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.solver = mock_delay(2)
    task.working_limit = 1
    log = eval(task, fail_on_error=False, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["status"], row["error_kind"]) == ("failed", None)
    assert row["checks"]["erc_number"]["passed"] is False
    assert "working limit 1" in row["checks"]["erc_number"]["reason"]
    assert row["limit"]["type"] == "working"


def test_completed_epochs_are_reused(folder, tmp_path):
    config = fixture_config()
    evaluation = load_eval(folder, config)
    first_success, first = run([evaluation], config, tmp_path / "results", answer="reference")
    second_success, second = run([evaluation], config, tmp_path / "results", answer="reference")
    assert (first_success, second_success) == (True, True)
    assert [row["status"] for row in second] == ["passed", "passed", "passed"]
    assert [(row["completed_at"], row["log_file"]) for row in second] == [
        (row["completed_at"], row["log_file"]) for row in first
    ]


def test_crashed_epoch_runs_again_without_repeating_finished_epochs(folder, tmp_path, monkeypatch):
    from ethevals.checks import CHECK_SOLVERS, CheckRun
    attempts = 0

    @solver
    def crash_once():
        async def solve(state, generate):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise RuntimeError("Transient provider failure.")
            return await generate(state)
        return solve

    monkeypatch.setitem(CHECK_SOLVERS, "quiz", lambda evaluation, answer: CheckRun(crash_once(), "8004"))
    config = fixture_config()
    config.concurrency = 1
    evaluation = load_eval(folder, config)
    output = tmp_path / "results"
    success, first = run([evaluation], config, output, answer="reference")
    assert success is False
    assert [row["status"] for row in first] == ["passed", "error", "passed"]
    success, second = run([evaluation], config, output, answer="reference")
    assert success is True
    assert [row["status"] for row in second] == ["passed", "passed", "passed"]
    assert [second[index]["completed_at"] == first[index]["completed_at"] for index in range(3)] == [True, False, True]
    assert len(list((output / "logs").rglob("*.eval"))) == 4
    assert attempts == 4


@pytest.mark.parametrize("kind", ["working", "token"])
def test_limits_are_final_failed_epochs(folder, tmp_path, monkeypatch, kind):
    import ethevals.runner as runner
    original = runner.build_task

    def limited(*args, **kwargs):
        task = original(*args, **kwargs)
        if kind == "working":
            task.solver = mock_delay(2)
            task.working_limit = 1
        else:
            task.token_limit = 1
        return task

    monkeypatch.setattr(runner, "build_task", limited)
    config = fixture_config()
    output = tmp_path / "results"
    evaluation = load_eval(folder, config)
    success, first = run([evaluation], config, output, answer="reference", epochs=1)
    assert success is True
    assert (first[0]["status"], (None if first[0]["status"] == "error" else first[0]["status"] == "passed")) == ("failed", False)
    assert f"{kind} limit" in first[0]["checks"]["erc_number"]["reason"]
    success, second = run([evaluation], config, output, answer="reference", epochs=1)
    assert success is True
    assert second == first


def test_store_keeps_old_evals_and_runs_only_edited_eval(folder, tmp_path):
    config = fixture_config()
    other = tmp_path / "concepts/other"
    shutil.copytree(folder, other)
    output = tmp_path / "results"
    success, first = run([load_eval(path, config) for path in [folder, other]], config, output, answer="reference", epochs=1)
    assert success is True
    path = folder / "eval.yaml"
    path.write_text(path.read_text() + "\n# Edited eval\n")
    success, second = run([load_eval(path, config) for path in [folder, other]], config, output, answer="reference", epochs=1)
    assert success is True
    assert [row["status"] for row in second] == ["passed", "passed"]
    old_other = next(row for row in first if row["eval_id"] == "concepts/other")
    assert next(row for row in second if row["eval_id"] == "concepts/other") == old_other
    stored = [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()]
    assert sorted(row["eval_id"] for row in stored) == ["concepts/other", "concepts/quiz", "concepts/quiz"]
    assert len(list((output / "logs").rglob("*.eval"))) == 3
    # A different selection retains every earlier identity in rows.jsonl.
    success, selected = run([load_eval(other, config)], config, output, answer="reference", epochs=1)
    assert success is True
    assert selected == [old_other]
    assert [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()] == stored


def test_prices_grader_and_model_selection_do_not_repeat_epochs(folder, tmp_path):
    config = fixture_config()
    config.grader.model = "mockllm/grader"
    for key, item in config.models.items():
        item.model = f"mockllm/{key}"
    evaluation = load_eval(folder, config)
    output = tmp_path / "results"
    success, first = run([evaluation], config, output, models=["opus-5.5"], modes=["vanilla"], epochs=1, budget=100)
    assert success is True
    config.prices[config.models["opus-5.5"].model].input = 99.0
    config.grader.model = "mockllm/gpt-5.5"
    config.time_limits["quiz"] = 400
    success, second = run([evaluation], config, output, models=["opus-5.5"], modes=["vanilla"], epochs=1, budget=100)
    assert success is True
    assert second == first
    success, third = run([evaluation], config, output, models=["gpt-5.5"], modes=["vanilla"], epochs=1, budget=100)
    assert success is True
    assert third[0]["model"] == "mockllm/gpt-5.5"
    stored = [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()]
    assert sorted(row["model"] for row in stored) == ["mockllm/gpt-5.5", "mockllm/opus-5.5"]
    config.models["opus-5.5"].effort = "medium"
    success, fourth = run([evaluation], config, output, models=["opus-5.5"], modes=["vanilla"], epochs=1, budget=100)
    assert success is True
    assert fourth[0]["effort"] == "medium"
    assert len(list((output / "logs").rglob("*.eval"))) == 3


def test_setup_failure_has_unknown_cost(folder, tmp_path):
    from inspect_ai.log import EvalError
    config = fixture_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    # A task-level failure has no sample usage to assign to either role.
    log.samples = []
    log.status = "error"
    log.error = EvalError(message="Sandbox startup failed.", traceback="", traceback_ansi="")
    log.eval.metadata.update(cost_source="computed:test")
    row = results_rows(log)[0]
    assert (row["status"], row["error_reason"]) == ("error", "Sandbox startup failed.")
    assert (row["model_cost_usd"], row["cost_source"], row["grader_cost_usd"], row["cost_source"]) == (
        None, "unavailable", None, "unavailable")


def test_kill_and_resume_keeps_completed_epochs(folder, tmp_path):
    output = tmp_path / "results"
    config = fixture_config()
    config.concurrency = 1
    config_path = tmp_path / "serial.yaml"
    config_path.write_text(yaml.safe_dump(config.model_dump()))
    command = [sys.executable, str(Path(__file__).with_name("resume_check.py")),
               str(folder), str(output), str(config_path)]
    environment = {key: value for key, value in os.environ.items() if key != "OPENROUTER_API_KEY"}
    completed = []
    with (tmp_path / "killed.txt").open("w") as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and process.poll() is None:
                for path in (output / "logs").glob("*.eval"):
                    try:
                        log = read_eval_log(path)
                    except ValueError as error:
                        if "EOCD not found" not in str(error):
                            raise
                        # Inspect has opened the ZIP but has not written its directory yet.
                        continue
                    completed.extend((log.eval.metadata["epoch"], sample.completed_at)
                                     for sample in log.samples or [] if sample.scores)
                if completed:
                    break
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
    assert process.returncode == -signal.SIGKILL
    assert len(completed) == 1
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()]
    assert [(row["epoch"], row["status"]) for row in rows] == [(1, "passed"), (2, "passed"), (3, "passed")]
    assert [(row["epoch"], row["completed_at"]) for row in rows if row["epoch"] == completed[0][0]] == completed


def test_errors_stop_after_two_attempts(tmp_path, monkeypatch):
    @solver
    def crash():
        async def solve(state, generate):
            raise RuntimeError("Container transport failed.")
        return solve

    monkeypatch.setitem(CHECK_SOLVERS, "quiz", lambda evaluation, answer: CheckRun(crash()))
    config = fixture_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    output = tmp_path / "results"
    for attempt, expected_success in [(1, False), (2, False), (2, True)]:
        success, rows = run([evaluation], config, output, answer="reference", epochs=1)
        assert success is expected_success
        assert (rows[0]["status"], rows[0]["attempt"]) == ("error", attempt)
    assert len(list((output / "logs").glob("*.eval"))) == 2
    success, rows = run([evaluation], config, output, answer="reference", epochs=1, retry_errors=True)
    assert (success, rows[0]["status"], rows[0]["attempt"]) == (False, "error", 3)
    assert rows[0]["checks"] == {}
    success, rows = run([evaluation], config, output, answer="reference", epochs=1)
    assert (success, rows[0]["attempt"]) == (True, 3)


@pytest.mark.parametrize("budget", [5.0, 0.01])
def test_cost_limit_discounts_cache_for_a_forty_call_build(tmp_path, budget):
    config = fixture_config()
    config.cost_limit = budget
    config.models["opus-5.5"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    task = build_task(evaluation, config, "opus-5.5", "vanilla", None, 1)

    @solver
    def forty_calls():
        async def solve(state, generate):
            for _ in range(40):
                state = await generate(state)
            return state
        return solve

    def reply(messages, tools, tool_choice, config):
        output = ModelOutput.from_content("mockllm/model", "8004")
        output.usage = ModelUsage(input_tokens=1000, input_tokens_cache_read=19000, output_tokens=1000, total_tokens=21000)
        return output

    task.solver = forty_calls()
    task.model = get_model("mockllm/model", custom_outputs=reply)
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    assert (row["status"], row["total_tokens"]) == (("passed", 840000) if budget == 5.0 else ("failed", 21000))
    assert row["model_cost_usd"] == pytest.approx(1.58 if budget == 5.0 else 0.0395)
    assert row["grader_cost_usd"] == 0


@pytest.mark.docker
def test_agent_limit_skips_snapshot_and_unavailable_grader(scoring_case):
    from support import mock_delay
    scoring_case["task"].working_limit = 1
    scoring_case["task"].solver = mock_delay(2)
    row = scoring_case["run"]([RuntimeError("Grader unavailable")])
    assert (row["status"], (scoring_case["log"].samples[0].role_usage["grader"].total_tokens if "grader" in scoring_case["log"].samples[0].role_usage else 0)) == ("failed", 0)
    assert row["limit"]["type"] == "working"
    assert all(not check["passed"] and "working limit" in check["reason"] for check in row["checks"].values())
    assert scoring_case["requests"] == []


@pytest.mark.docker
def test_grader_provider_failure_retains_tests_score(scoring_case):
    row = scoring_case["run"]([YES, RuntimeError("Provider unavailable: 503")])
    assert row["status"] == "error"
    assert set(row["checks"]) == {"forge:compile", CHECK}
    assert "503" in row["error_reason"]


@pytest.mark.docker
@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("exhausted", [False, True])
def test_grader_retries_transient_failures_with_a_bound(scoring_case, monkeypatch, status, exhausted):
    import httpx
    from inspect_ai.model._providers.mockllm import MockLLM
    from tenacity import wait_none

    monkeypatch.setattr(MockLLM, "should_retry", lambda self, error: isinstance(error, httpx.HTTPStatusError))
    monkeypatch.setattr(MockLLM, "retry_wait", lambda self: wait_none())
    response = httpx.Response(status, request=httpx.Request("POST", "https://provider.invalid/grade"))
    error = httpx.HTTPStatusError(f"Provider unavailable: {status}", request=response.request, response=response)
    # The third failed attempt exhausts provider retries. A later success must remain unread.
    replies = [YES, error, error, *([error] if exhausted else []), YES]
    row = scoring_case["run"](replies)
    assert row["status"] == ("error" if exhausted else "passed")
    if exhausted:
        assert "HTTPStatusError" in row["error_reason"]
    else:
        assert row["checks"]["rubric:protects_holders"] == {"passed": True, "reason": "Uses standard transfers."}
        assert (scoring_case["log"].samples[0].role_usage["grader"].total_tokens if "grader" in scoring_case["log"].samples[0].role_usage else 0) == 400


@pytest.mark.docker
def test_grader_no_is_a_failed_check(scoring_case):
    row = scoring_case["run"]([YES, NO])
    assert row["status"] == "failed"
    assert row["checks"]["rubric:protects_holders"] == {"passed": False, "reason": "Owner can seize tokens."}
    assert (scoring_case["log"].samples[0].role_usage["grader"].total_tokens if "grader" in scoring_case["log"].samples[0].role_usage else 0) == 400


@pytest.mark.docker
@pytest.mark.parametrize("reply", ["No JSON.", '```json\n' + YES + '\n```'])
def test_invalid_grader_replies_are_a_bounded_error(scoring_case, reply):
    row = scoring_case["run"]([reply, reply])
    assert (row["status"], (scoring_case["log"].samples[0].role_usage["grader"].total_tokens if "grader" in scoring_case["log"].samples[0].role_usage else 0)) == ("error", 400)
    assert "after two calls" in row["error_reason"]
    assert set(row["checks"]) == {"forge:compile", CHECK}


@pytest.mark.docker
def test_grader_budget_error_retains_tests_score(scoring_case):
    row = scoring_case["run"]([YES, YES], budget=0.004)
    assert (row["status"], row["limit"]) == ("error", None)
    assert "Grader cost limit reached." in row["error_reason"]
    assert row["checks"][CHECK] == {"passed": True, "reason": "Test passed."}


@pytest.mark.docker
def test_compile_failure_records_one_check_and_skips_grader(scoring_case):
    scoring_case["task"].solver = submit_source("pragma solidity ^0.8.30; contract Token { uint value = ; }")
    row = scoring_case["run"]([RuntimeError("The grader must not run")])
    assert (row["status"], (scoring_case["log"].samples[0].role_usage["grader"].total_tokens if "grader" in scoring_case["log"].samples[0].role_usage else 0)) == ("failed", 0)
    assert row["checks"] == {
        "forge:compile": {"passed": False, "reason": "Error (6933): Expected primary expression."}}


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


def test_fold_is_order_independent_and_sorts_epochs_as_numbers():
    old = {"eval_id": "a", "eval_hash": "a", "epoch": 2, "attempt": 1, "status": "error", "completed_at": "2026-01-01"}
    later = {**old, "status": "passed", "completed_at": "2026-01-02"}
    last = {**later, "epoch": 10}
    for groups in itertools.permutations([[old], [later], [last]]):
        assert [(r["epoch"], r["status"]) for r in fold_rows(*groups)] == [(2, "passed"), (10, "passed")]


def test_runner_exception_after_eval_retains_rows_and_plan_reads_logs(tmp_path, monkeypatch):
    import ethevals.runner as runner
    config, evaluation = catalog_quiz()
    real_eval = runner.eval

    def interrupted(*args, **kwargs):
        real_eval(*args, **kwargs)
        raise RuntimeError("Runner failed after eval")

    monkeypatch.setattr(runner, "eval", interrupted)
    with pytest.raises(RuntimeError, match="after eval"):
        run([evaluation], config, tmp_path, answer="reference", epochs=1)
    row = read_rows(tmp_path / "rows.jsonl")[0]
    assert (row["status"], row["attempt"]) == ("passed", 1)
    (tmp_path / "rows.jsonl").unlink()
    agents_for, _ = select_actors(config, answer="reference", planning=True)
    report = plan([evaluation], config, agents_for, previous_rows(tmp_path), epochs=1).report
    assert (report["missing_epochs"], report["worst_case_usd"]) == (0, 0)


def test_fold_keeps_committed_rows_and_replaces_retried_identity(tmp_path):
    old = {"eval_id": "concepts/a", "eval_hash": "old", "model": "mockllm/model", "mode": "vanilla", "epoch": 1,
           "status": "passed", "attempt": 1}
    error = {**old, "eval_hash": "current", "status": "error"}
    retry = {**error, "status": "failed", "attempt": 2}
    new = {**old, "eval_id": "concepts/b"}
    path = tmp_path / "rows.jsonl"
    write_rows(path, fold_rows([old, error], [retry, new]))
    assert [(r["eval_id"], r["eval_hash"], r["status"], r["attempt"]) for r in read_rows(path)] == [
        ("concepts/a", "current", "failed", 2), ("concepts/a", "old", "passed", 1), ("concepts/b", "old", "passed", 1)]
    content, mtime = path.read_bytes(), path.stat().st_mtime_ns
    write_rows(path, fold_rows(read_rows(path), []))
    assert path.read_bytes() == content
    assert path.stat().st_mtime_ns == mtime


@pytest.mark.docker
@pytest.mark.parametrize("script,status,reason", [
    (b'print("x" * (11 * 1024 * 1024))', "error", "malformed JSON"),
    (b'print("not JSON")', "error", "malformed JSON"),
    (b'raise ValueError("bad amount")', "error", "ValueError: bad amount"),
    (b'import os, signal; os.kill(os.getpid(), signal.SIGKILL)', "error", "exited 137"),
])
def test_check_script_failures_through_task(tmp_path, script, status, reason):
    import shutil
    config = fixture_config()
    folder = tmp_path / "transactions/script"
    shutil.copytree(ROOT / "evals/transactions/send-six-decimal-token", folder)
    (folder / "scorer/check.py").write_bytes(b"#!/usr/bin/env python3\n" + script)
    evaluation = load_eval(folder, config)
    success, rows = run([evaluation], config, tmp_path / "results", answer="empty", epochs=1)
    row = rows[0]
    assert (success, row["status"]) == (status != "error", status)
    assert reason in row["error_reason"]


@pytest.mark.docker
@pytest.mark.parametrize("local_oom,cli_code", [(True, 137), (False, 137), (True, 1)])
def test_agent_container_death_through_exported_rows(tmp_path, monkeypatch, local_oom, cli_code):
    from ethevals import agents
    from inspect_ai.util import sandbox
    from ethevals.sandboxes import runner_exec
    config = fixture_config()
    config.models["opus-5.5"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    compose = prepare_compose(evaluation, tmp_path)
    document = yaml.safe_load(compose.read_bytes())
    document["services"]["default"]["mem_limit"] = "128m"
    compose.write_text(yaml.safe_dump(document))

    async def killed(state, generate):
        command = ["/usr/bin/perl", "-e", '$allocation = "x" x (512 * 1024 * 1024); sleep 1'] if local_oom else [
            "/bin/sh", "-c", "kill -9 $$"]
        result = await runner_exec(sandbox("default"), command)
        if not result.success:
            assert result.returncode == 137
            # The CLI can survive its child's OOM and fail later for another cause.
            if cli_code == 1:
                result = await runner_exec(sandbox("default"), ["/bin/sh", "-c", "exit 1"])
            raise RuntimeError(f"Error executing claude code agent {result.returncode}: CLI failure")
        raise AssertionError("The death proof survived")

    monkeypatch.setitem(agents.HARNESSES, "claude_code", replace(
        agents.HARNESSES["claude_code"], factory=lambda *a, **kw: killed, version="proof"))
    actors_for, _ = select_actors(config, agents=["claude-code-opus-5.5"], modes=["internet"])
    task = actor_task(evaluation, config, actors_for(evaluation)[0][1], check_grader(), "internet", 1, compose)
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    assert row["status"] == "error", row
    assert f"Error executing claude code agent {cli_code}" in row["error_reason"]


@pytest.mark.docker
def test_non_utf8_source_matches_real_forge_and_fails_checks(tmp_path):
    import anyio
    from ethevals.scorers import forge, prepare_forge
    config = fixture_config()
    original = load_eval(ROOT / "inspect-runner/tests/fixtures/building/erc20-points-token", config)
    source = b"pragma solidity =0.8.30; //\xff\ncontract BuilderPoints {}"
    with containers(tmp_path / "raw") as boxes:
        async def capture():
            box = boxes["scorer"]
            await prepare_forge(box, {"src/BuilderPoints.sol": b"pragma solidity =0.8.30; contract BuilderPoints {}"}, original.files)
            await box.write_file("/workspace/src/BuilderPoints.sol", source)
            return await forge(box, timeout=180)
        result = anyio.run(capture)
        assert result.returncode == 1
        assert "stream did not contain valid UTF-8" in result.stderr
        (tmp_path / "forge-invalid-utf8.json").write_text(json.dumps(result.model_dump() if hasattr(result, "model_dump") else vars(result)))
    files = {**original.files, "workspace/src/BuilderPoints.sol": source}
    evaluation = replace(original, files=files, hash=content_hash(files))
    success, rows = run([evaluation], config, tmp_path / "scored", answer="empty", epochs=1)
    assert success
    assert (rows[0]["status"], (None if rows[0]["status"] == "error" else rows[0]["status"] == "passed")) == ("failed", False)
    assert {check["reason"] for check in rows[0]["checks"].values()} == {"Solidity source is not valid UTF-8: src/BuilderPoints.sol"}
