from pathlib import Path
import itertools
import json
import shutil

from ethevals.actors import select_actors
from ethevals.checks import CHECK_SOLVERS, CheckRun
from ethevals.loader import load_eval
from ethevals.planning import plan
from ethevals.rows import fold_rows, previous_rows, read_rows, results_rows, write_rows
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelCost, ModelInfo, ModelOutput, ModelUsage, get_model, set_model_info
from inspect_ai.scorer import accuracy, scorer
from inspect_ai.solver import solver
from inspect_ai.util import sandbox
import pytest

from support import build_task, catalog_quiz, fixture_config, mock_delay, run


ROOT = Path(__file__).resolve().parents[2]


@scorer(metrics={"*": [accuracy()]})
def with_grader(underlying):

    async def score(state, target):
        await get_model(role="grader").generate("Grade this answer.")
        return await underlying(state, target)
    return score


YES = '{"passed": true, "reason": "Uses standard transfers."}'


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


def test_limits_are_final_failed_epochs(folder, tmp_path, monkeypatch):
    import ethevals.runner as runner
    original = runner.build_task

    def limited(*args, **kwargs):
        task = original(*args, **kwargs)
        task.solver = mock_delay(2)
        task.working_limit = 1
        return task

    monkeypatch.setattr(runner, "build_task", limited)
    config = fixture_config()
    output = tmp_path / "results"
    evaluation = load_eval(folder, config)
    success, first = run([evaluation], config, output, answer="reference", epochs=1)
    assert success is True
    assert (first[0]["status"], (None if first[0]["status"] == "error" else first[0]["status"] == "passed")) == ("failed", False)
    assert "working limit" in first[0]["checks"]["erc_number"]["reason"]
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


@pytest.mark.parametrize("reply", [RuntimeError("Provider unavailable"), "No JSON."])
def test_grader_failure_retains_primary_score(quiz_scoring_case, reply):
    row = quiz_scoring_case["run"]([reply, reply])
    assert row["status"] == "error"
    assert row["checks"] == {"answer": {"passed": True, "reason": "Answer matches the target."}}


def test_grader_budget_error_retains_primary_score(quiz_scoring_case):
    row = quiz_scoring_case["run"]([YES], budget=0.001)
    assert (row["status"], row["limit"]) == ("error", None)
    assert "Grader cost limit reached." in row["error_reason"]
    assert row["checks"] == {"answer": {"passed": True, "reason": "Answer matches the target."}}


@pytest.mark.docker
def test_compile_failure_records_one_check_and_skips_grader(scoring_case):
    scoring_case["task"].solver = submit_source("pragma solidity ^0.8.30; contract Token { uint value = ; }")
    row = scoring_case["run"]([RuntimeError("The grader must not run")])
    assert (row["status"], (scoring_case["log"].samples[0].role_usage["grader"].total_tokens if "grader" in scoring_case["log"].samples[0].role_usage else 0)) == ("failed", 0)
    assert row["checks"] == {
        "forge:compile": {"passed": False, "reason": "Error (6933): Expected primary expression."}}


def test_operator_stop_is_an_error_and_skips_scoring(quiz_scoring_case):
    from inspect_ai._util.exception import TerminateSampleError

    @solver
    def stopped():
        async def solve(state, generate):
            raise TerminateSampleError("Stopped by operator")
        return solve

    quiz_scoring_case["task"].solver = stopped()
    row = quiz_scoring_case["run"]([])
    assert (row["status"], row["limit"]["type"]) == ("error", "operator")
    assert "Stopped by operator" in row["error_reason"]


def test_wall_backstop_is_an_error(quiz_scoring_case):
    from support import mock_delay
    quiz_scoring_case["task"].solver = mock_delay(2)
    quiz_scoring_case["task"].time_limit = 1
    row = quiz_scoring_case["run"]([])
    assert (row["status"], row["limit"]["type"]) == ("error", "time")
    assert row["working_seconds"] < quiz_scoring_case["log"].eval.metadata["working_limit_seconds"]


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
