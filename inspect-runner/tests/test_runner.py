import json
import shutil
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelCost, ModelInfo, ModelOutput, ModelUsage, get_model, set_model_info
from inspect_ai.scorer import accuracy, scorer
from inspect_ai.solver import solver

from ethevals.config import load_config
from ethevals.loader import eval_hash, load_eval
from ethevals.rows import results_rows
from support import run
from ethevals.checks import mock_delay
from support import build_task
from ethevals.files import inline_file
from ethevals.scorers import named_checks

def scorer_yaml(text):
    return yaml.safe_dump({"scorers": [yaml.safe_load(text)]})


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def folder(tmp_path):
    target = tmp_path / "concepts" / "quiz"
    shutil.copytree(ROOT / "evals/concepts/agent-registries", target)
    return target


@pytest.mark.parametrize("file,addition,key", [
    ("eval.yaml", "unexpected: true\n", "unexpected"),
    ("scorer/scorer.yaml", "unexpected: true\n", "unexpected"),
    ("eval.yaml", "addresses: {registry: 0x1234}\n", "addresses"),
])
def test_loader_rejects_unknown_keys(folder, file, addition, key):
    path = folder / file
    path.write_text(path.read_text() + addition)
    with pytest.raises(ValueError) as error:
        load_eval(folder, load_config())
    assert str(path) in str(error.value)
    assert key in str(error.value)


@pytest.mark.parametrize("target", ["8004", "1.10", "0x1234", '["8004", 42]'])
def test_loader_rejects_numeric_targets(folder, target):
    path = folder / "scorer/scorer.yaml"
    path.write_text(f"scorers:\n  - kind: target\n    target: {target}\n")
    with pytest.raises(ValueError) as error:
        load_eval(folder, load_config())
    assert f"{path}: target" in str(error.value)


def test_loader_requires_scorer_file(folder):
    path = folder / "scorer/scorer.yaml"
    path.unlink()
    with pytest.raises(ValueError) as error:
        load_eval(folder, load_config())
    assert str(path) in str(error.value)


def test_loader_preserves_target_and_prompt(folder):
    (folder / "workspace/.gitkeep").unlink()
    (folder / "eval.yaml").write_text("type: quiz\nmotivation: Test a literal answer.\nprompt: Say hello.\nmodes: [internet]\n")
    (folder / "scorer/scorer.yaml").write_text(scorer_yaml('kind: target\ntarget: ["hello", "hi"]\n'))
    (folder / "workspace/hello.txt").write_text("public workspace")
    (folder / "scorer/secret.txt").write_text("private scorer")
    sample = load_eval(folder, load_config()).sample()
    assert (sample.id, sample.input, sample.target) == ("concepts/quiz", "Say hello.", ["hello", "hi"])
    assert sample.files == {"/workspace/hello.txt": inline_file(b"public workspace")}


def test_hash_tracks_every_file_and_name(folder):
    original = eval_hash(folder)
    path = folder / "workspace/code.txt"
    path.write_text("hello")
    added = eval_hash(folder)
    assert added != original
    path.write_text("goodbye")
    changed = eval_hash(folder)
    assert changed != added
    path.rename(folder / "workspace/renamed.txt")
    assert eval_hash(folder) != changed
    (folder / "workspace/renamed.txt").unlink()
    assert eval_hash(folder) == original


@pytest.mark.parametrize("answer,expected", [("reference", True), ("empty", False), ("default", False)])
def test_quizzes_through_real_pipeline(tmp_path, answer, expected):
    config = load_config()
    evals = [load_eval(path, config) for path in sorted((ROOT / "evals/concepts").iterdir())]
    output = tmp_path / answer
    success, rows = run(evals, config, output, answer=answer)
    assert success is True
    assert [(row["eval_id"], row["epoch"], row["passed"]) for row in rows] == [
        ("concepts/agent-registries", 1, expected), ("concepts/agent-registries", 2, expected),
        ("concepts/agent-registries", 3, expected), ("concepts/wei-per-ether", 1, expected),
        ("concepts/wei-per-ether", 2, expected), ("concepts/wei-per-ether", 3, expected),
    ]
    assert [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()] == rows
    for row in rows:
        check_name = "erc_number" if row["eval_id"].endswith("agent-registries") else "wei_conversion"
        reason = "Answer matches the target." if expected else "The answer is empty." if answer == "empty" else "Answer does not match the target."
        assert row["checks"] == {check_name: {"passed": expected, "reason": reason}}
        assert (row["model_cost_usd"], row["model_cost_source"], row["grader_tokens"]) == (0.0, "mock", 0)
        assert Path(row["log_file"]).is_absolute() is False
        log = read_eval_log(output / row["log_file"])
        sample = next(sample for sample in log.samples if sample.epoch == row["log_epoch"])
        assert (sample.id, sample.uuid) == (row["log_sample_id"], row["sample_uuid"])
        calls = [event for event in sample.events if event.event == "model"]
        assert len(calls) == 1
        assert calls[0].tools == []


@pytest.mark.parametrize("method,answer,expected", [("pattern", "ERC 8004", True), ("pattern", "ERC 20", False), ("match", "20", False)])
def test_target_methods_from_real_log(folder, tmp_path, method, answer, expected):
    path = folder / "scorer/scorer.yaml"
    path.write_text(scorer_yaml('kind: target\nname: number\ntarget: "8004"\nmethod: ' + method + ('\npattern: "ERC ([0-9]+)"\n' if method == "pattern" else "\n")))
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.model = get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert row["passed"] is expected
    assert row["checks"]["number"]["passed"] is expected


@scorer(metrics=[accuracy()])
def with_grader(underlying):

    async def score(state, target):
        await get_model(role="grader").generate("Grade this answer.")
        return await underlying(state, target)
    return score


def test_rows_split_grader_usage_for_the_same_model(folder, tmp_path):
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.metadata.update(answer_kind=None, cost_source="computed:test", grader_cost_source="computed:grader", prices={"input": 1, "output": 2})
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
    assert (row["model_tokens"], row["grader_tokens"], row["total_tokens"]) == (14, 10, 24)
    assert row["model_cost_usd"] == pytest.approx(0.000018)
    assert row["grader_cost_usd"] == pytest.approx(0.000013)
    assert (row["model_cost_source"], row["grader_cost_source"]) == ("computed:test", "computed:grader")
    assert row["prices"] == {"input": 1, "output": 2}


@solver
def crash():
    async def solve(state, generate):
        raise RuntimeError("Harness crashed in the test.")
    return solve


def test_error_is_distinct_from_failed_answer(folder, tmp_path):
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.solver = crash()
    log = eval(task, fail_on_error=False, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["status"], row["passed"], row["error_kind"]) == ("error", None, "execution")
    assert "Harness crashed in the test." in row["error_reason"]


def test_time_limit_is_a_failed_check(folder, tmp_path):
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.solver = mock_delay(2)
    task.time_limit = 1
    log = eval(task, fail_on_error=False, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["status"], row["passed"], row["error_kind"]) == ("failed", False, None)
    assert row["checks"]["erc_number"]["passed"] is False
    assert "time limit 1" in row["checks"]["erc_number"]["reason"]
    assert row["limit"]["type"] == "time"


def test_choice_target_list_accepts_either_letter(folder, tmp_path):
    (folder / "eval.yaml").write_text("type: quiz\nmotivation: Check accepted alternatives.\nprompt: Select a greeting.\nmodes: [internet]\nchoices: [hello, hi, goodbye]\n")
    (folder / "scorer/scorer.yaml").write_text(scorer_yaml('kind: target\nmethod: choice\ntarget: ["A", "B"]\n'))
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, "internet", "reference", 1)
    task.model = get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", "ANSWER: B")])
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert row["checks"] == {"answer": {"passed": True, "reason": "Answer matches the target."}}


def test_completed_epochs_are_reused(folder, tmp_path):
    config = load_config()
    evaluation = load_eval(folder, config)
    first_success, first = run([evaluation], config, tmp_path / "results", answer="reference")
    second_success, second = run([evaluation], config, tmp_path / "results", answer="reference")
    assert (first_success, second_success) == (True, True)
    assert [row["status"] for row in second] == ["passed", "passed", "passed"]
    assert [(row["sample_uuid"], row["log_file"]) for row in second] == [
        (row["sample_uuid"], row["log_file"]) for row in first
    ]


def cli(*args):
    environment = {key: value for key, value in os.environ.items() if key != "OPENROUTER_API_KEY"}
    return subprocess.run([sys.executable, "-m", "ethevals.cli", *map(str, args)],
                          cwd=ROOT, env=environment, text=True, capture_output=True, timeout=60)


@pytest.mark.parametrize("pattern,reference", [("ERC ([0-9]+)", "ERC 8004"), ("ERC-?([0-9]+)", "ERC-8004")])
def test_pattern_check_through_cli(folder, tmp_path, pattern, reference):
    (folder / "scorer/scorer.yaml").write_text(scorer_yaml(
        f'kind: target\ntarget: "8004"\nmethod: pattern\npattern: "{pattern}"\nreference: "{reference}"\n'
    ))
    output = tmp_path / "results"
    for invocation in range(2):
        if invocation:
            path = folder / "eval.yaml"
            path.write_text(path.read_text() + "\n# Author edited the eval.\n")
        result = cli("check", "--evals", folder, "--epochs", 1, "--output", output)
        assert result.returncode == 0, result.stdout + result.stderr
        reference_rows = [json.loads(line) for line in (output / "reference/rows.jsonl").read_text().splitlines()]
        empty_rows = [json.loads(line) for line in (output / "empty/rows.jsonl").read_text().splitlines()]
        assert [row["status"] for row in reference_rows] == ["passed"] * (invocation + 1)
        assert [row["status"] for row in empty_rows] == ["failed"] * (invocation + 1)
    assert len(list((output / "reference/logs").rglob("*.eval"))) == 2


def test_check_reruns_changed_scorer(folder, tmp_path, monkeypatch):
    from ethevals.cli import main
    from ethevals.scorers import SCORERS
    from dataclasses import replace
    from inspect_ai.scorer import Score

    monkeypatch.setattr(sys, "argv", ["ethevals", "check", "--evals", str(folder),
                                    "--epochs", "1", "--output", str(tmp_path / "results")])
    assert main() == 0

    def always_pass(config, folder):
        async def score(state, target, submission=None):
            return Score(value="C", metadata={"checks": {config.name: {"passed": True, "reason": "Broken scorer."}}})
        return score

    monkeypatch.setitem(SCORERS, "target", replace(SCORERS["target"], build=always_pass))
    assert main() == 1
    empty = json.loads((tmp_path / "results/empty/rows.jsonl").read_text())
    assert empty["checks"] == {"erc_number": {"passed": True, "reason": "Broken scorer."}}


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
    config = load_config()
    config.max_tasks = config.max_samples = 1
    evaluation = load_eval(folder, config)
    output = tmp_path / "results"
    success, first = run([evaluation], config, output, answer="reference")
    assert success is False
    assert [row["status"] for row in first] == ["passed", "error", "passed"]
    success, second = run([evaluation], config, output, answer="reference")
    assert success is True
    assert [row["status"] for row in second] == ["passed", "passed", "passed"]
    assert [second[index]["sample_uuid"] == first[index]["sample_uuid"] for index in range(3)] == [True, False, True]
    assert len(list((output / "logs").rglob("*.eval"))) == 4
    assert attempts == 4


@pytest.mark.parametrize("kind", ["time", "token"])
def test_limits_are_final_failed_epochs(folder, tmp_path, monkeypatch, kind):
    import ethevals.runner as runner
    original = runner.build_task

    def limited(*args, **kwargs):
        task = original(*args, **kwargs)
        if kind == "time":
            task.solver = mock_delay(2)
            task.time_limit = 1
        else:
            task.token_limit = 1
        return task

    monkeypatch.setattr(runner, "build_task", limited)
    config = load_config()
    output = tmp_path / "results"
    evaluation = load_eval(folder, config)
    success, first = run([evaluation], config, output, answer="reference", epochs=1)
    assert success is True
    assert (first[0]["status"], first[0]["passed"]) == ("failed", False)
    assert f"{kind} limit" in first[0]["checks"]["erc_number"]["reason"]
    success, second = run([evaluation], config, output, answer="reference", epochs=1)
    assert success is True
    assert second == first


def test_store_keeps_old_evals_and_runs_only_edited_eval(folder, tmp_path):
    config = load_config()
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
    config = load_config()
    config.grader.model = "mockllm/grader"
    for key, item in config.models.items():
        item.model = f"mockllm/{key}"
    evaluation = load_eval(folder, config)
    output = tmp_path / "results"
    success, first = run([evaluation], config, output, models=["opus"], epochs=1)
    assert success is True
    config.models["opus"].prices.input = 99.0
    config.grader.model = "mockllm/codex"
    config.time_limit = 400
    success, second = run([evaluation], config, output, models=["opus"], epochs=1)
    assert success is True
    assert second == first
    success, third = run([evaluation], config, output, models=["codex"], epochs=1)
    assert success is True
    assert third[0]["model"] == "mockllm/codex"
    stored = [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()]
    assert sorted(row["model"] for row in stored) == ["mockllm/codex", "mockllm/opus"]
    config.models["opus"].effort = "low"
    success, fourth = run([evaluation], config, output, models=["opus"], epochs=1)
    assert success is True
    assert fourth[0]["effort"] == "low"
    assert len(list((output / "logs").rglob("*.eval"))) == 3


def test_declared_modes_skip_ineligible_evals(folder, tmp_path):
    path = folder / "eval.yaml"
    path.write_text(path.read_text().replace("[vanilla, internet]", "[internet]"))
    config = load_config()
    vanilla = load_eval(ROOT / "evals/concepts/wei-per-ether", config)
    internet = load_eval(folder, config)
    success, rows = run([internet, vanilla], config, tmp_path / "results", answer="reference", epochs=1)
    assert success is True
    assert [(row["eval_id"], row["mode"], row["status"]) for row in rows] == [
        ("concepts/wei-per-ether", "vanilla", "passed")]
    result = cli("check", "--evals", folder, vanilla.folder, "--epochs", 1, "--output", tmp_path / "check")
    assert result.returncode == 0, result.stdout + result.stderr
    path.write_text(path.read_text().replace("[internet]", "[internet, skills]"))
    assert load_eval(folder, config).declaration.modes == ["internet", "skills"]
    with pytest.raises(ValueError, match="No evals declare a selected mode"):
        run([internet], config, tmp_path / "none", modes=["skills"], answer="reference")


def test_hash_ignores_local_artifacts_but_includes_new_author_files(folder):
    (folder / "workspace/.gitkeep").unlink()
    original = eval_hash(folder)
    (folder / ".DS_Store").write_bytes(b"Finder")
    for name in ["out", "cache", "lib", "__pycache__"]:
        path = folder / "workspace" / name
        path.mkdir()
        (path / "generated").write_text("local artifact")
    assert eval_hash(folder) == original
    (folder / "workspace/code.sol").write_text("contract New {}")
    assert eval_hash(folder) != original
    assert load_eval(folder, load_config()).sample().files == {
        "/workspace/code.sol": inline_file(b"contract New {}")}


def test_validate_rejects_effort_typo(folder, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text((ROOT / "inspect-runner/ethevals/config.yaml").read_text().replace("effort: high", "effort: hihg"))
    result = cli("validate", "--evals", folder, "--config", path)
    assert result.returncode == 2
    assert "models.opus.effort" in result.stderr


def test_selected_modes_cross_only_declared_modes(folder, tmp_path):
    config = load_config()
    evaluation = load_eval(folder, config)
    success, rows = run([evaluation], config, tmp_path / "results", answer="reference", epochs=1,
                        modes=["vanilla", "internet", "skills"])
    assert success is True
    assert [(row["mode"], row["status"]) for row in rows] == [("internet", "passed"), ("vanilla", "passed")]


def test_unknown_grader_cost_keeps_known_model_cost(folder, tmp_path):
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    log.eval.metadata.update(answer_kind=None, model="mockllm/agent", grader_model="mockllm/grader",
                             cost_source="computed:test", grader_cost_source="computed:grader")
    # The exporter consumes persisted usage, including an unpriced grader.
    log.samples[0].model_usage = {
        "mockllm/agent": ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14, total_cost=0.000018),
        "mockllm/grader": ModelUsage(input_tokens=7, output_tokens=3, total_tokens=10),
    }
    log.samples[0].role_usage = {"grader": ModelUsage(input_tokens=7, output_tokens=3, total_tokens=10)}
    row = results_rows(log)[0]
    assert (row["model_cost_usd"], row["model_cost_source"]) == (0.000018, "computed:test")
    assert (row["grader_cost_usd"], row["grader_cost_source"]) == (None, "unavailable")
    assert (row["model_tokens"], row["grader_tokens"]) == (14, 10)


def test_setup_failure_has_unknown_cost(folder, tmp_path):
    from inspect_ai.log import EvalError
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    # A task-level failure has no sample usage to assign to either role.
    log.samples = []
    log.status = "error"
    log.error = EvalError(message="Sandbox startup failed.", traceback="", traceback_ansi="")
    log.eval.metadata.update(answer_kind=None, cost_source="computed:test")
    row = results_rows(log)[0]
    assert (row["status"], row["error_reason"]) == ("error", "Sandbox startup failed.")
    assert (row["model_cost_usd"], row["model_cost_source"], row["grader_cost_usd"], row["grader_cost_source"]) == (
        None, "unavailable", None, "unavailable")


def test_kill_and_resume_keeps_completed_epochs(folder, tmp_path):
    output = tmp_path / "results"
    config = load_config()
    config.max_tasks = config.max_samples = 1
    config_path = tmp_path / "serial.yaml"
    config_path.write_text(yaml.safe_dump(config.model_dump()))
    command = [sys.executable, "-m", "ethevals.cli", "run", "--evals", str(folder), "--answer", "reference",
               "--epochs", "3", "--mock-delay", "2", "--output", str(output), "--config", str(config_path)]
    environment = {key: value for key, value in os.environ.items() if key != "OPENROUTER_API_KEY"}
    completed = []
    with (tmp_path / "killed.txt").open("w") as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and process.poll() is None:
                for path in (output / "logs").glob("*.eval"):
                    log = read_eval_log(path)
                    completed.extend((log.eval.metadata["epoch"], sample.uuid)
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
    assert [(row["epoch"], row["sample_uuid"]) for row in rows if row["epoch"] == completed[0][0]] == completed
