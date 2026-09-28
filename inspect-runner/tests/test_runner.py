import json
import shutil
from pathlib import Path

import pytest
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelCost, ModelInfo, ModelOutput, ModelUsage, get_model, set_model_info
from inspect_ai.scorer import accuracy, scorer
from inspect_ai.solver import solver

from ethevals.config import load_config
from ethevals.loader import eval_hash, load_eval
from ethevals.rows import results_rows
from ethevals.runner import build_task, mock_delay, run
from ethevals.scorers import named_checks

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def folder(tmp_path):
    target = tmp_path / "concepts" / "quiz"
    shutil.copytree(ROOT / "evals/concepts/agent-registries", target)
    return target


@pytest.mark.parametrize("file,addition,key", [
    ("eval.yaml", "unexpected: true\n", "unexpected"),
    ("scorer/scorer.yaml", "unexpected: true\n", "unexpected"),
    ("eval.yaml", "addresses: {registry: 0x1234}\n", "addresses.registry"),
])
def test_loader_rejects_unknown_keys_and_numeric_addresses(folder, file, addition, key):
    path = folder / file
    path.write_text(path.read_text() + addition)
    with pytest.raises(ValueError) as error:
        load_eval(folder, load_config())
    assert str(path) in str(error.value)
    assert key in str(error.value)


@pytest.mark.parametrize("target", ["8004", "1.10", "0x1234", '["8004", 42]'])
def test_loader_rejects_numeric_targets(folder, target):
    path = folder / "scorer/scorer.yaml"
    path.write_text(f"kind: target\ntarget: {target}\n")
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
    (folder / "eval.yaml").write_text("type: quiz\nmotivation: Test a literal answer.\nprompt: Say hello.\nmodes: [vanilla]\n")
    (folder / "scorer/scorer.yaml").write_text('kind: target\ntarget: ["hello", "hi"]\n')
    sample = load_eval(folder, load_config()).sample()
    assert (sample.id, sample.input, sample.target) == ("concepts/quiz", "Say hello.", ["hello", "hi"])
    assert all("scorer" not in path for path in sample.files)


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
        assert json.loads(row["checks_json"]) == {check_name: {"passed": expected, "reason": reason}}
        assert (row["cost_usd"], row["cost_source"], row["grader_tokens"]) == (0.0, "mock", 0)
        log = read_eval_log(row["log_file"])
        sample = next(sample for sample in log.samples if sample.epoch == row["epoch"])
        assert (sample.id, sample.uuid) == (row["log_sample_id"], row["sample_uuid"])
        calls = [event for event in sample.events if event.event == "model"]
        assert len(calls) == 1
        assert calls[0].tools == []


@pytest.mark.parametrize("method,answer,expected", [("pattern", "ERC 8004", True), ("pattern", "ERC 20", False), ("match", "20", False)])
def test_target_methods_from_real_log(folder, tmp_path, method, answer, expected):
    path = folder / "scorer/scorer.yaml"
    path.write_text('kind: target\nname: number\ntarget: "8004"\nmethod: ' + method + ('\npattern: "ERC ([0-9]+)"\n' if method == "pattern" else "\n"))
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, config.modes.plain, "reference", 1)
    task.model = get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert row["passed"] is expected
    assert json.loads(row["checks_json"])["number"]["passed"] is expected


@scorer(metrics=[accuracy()])
def with_grader():
    underlying = named_checks("target", {"kind": "target", "target": "8004"})

    async def score(state, target):
        await get_model(role="grader").generate("Grade this answer.")
        return await underlying(state, target)
    return score


def test_rows_split_grader_usage_for_the_same_model(folder, tmp_path):
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, config.modes.plain, "reference", 1)
    task.metadata.update(answer_kind=None, cost_source="computed:test", prices={"input": 1, "output": 2})
    output = ModelOutput.from_content("mockllm/model", "8004")
    output.usage = ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14)
    grade = ModelOutput.from_content("mockllm/model", "yes")
    grade.usage = ModelUsage(input_tokens=7, output_tokens=3, total_tokens=10)
    set_model_info("mockllm/model", ModelInfo(cost=ModelCost(input=1, output=2, input_cache_read=0, input_cache_write=0)))
    task.model = get_model("mockllm/model", custom_outputs=[output])
    task.scorer = [with_grader()]
    log = eval(task, model_roles={"grader": get_model("mockllm/model", custom_outputs=[grade])},
               log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["model_tokens"], row["grader_tokens"], row["total_tokens"]) == (14, 10, 24)
    assert row["cost_usd"] == pytest.approx(0.000031)
    assert row["cost_source"] == "computed:test"


@solver
def crash():
    async def solve(state, generate):
        raise RuntimeError("Harness crashed in the test.")
    return solve


def test_error_is_distinct_from_failed_answer(folder, tmp_path):
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, config.modes.plain, "reference", 1)
    task.solver = crash()
    log = eval(task, fail_on_error=False, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["status"], row["passed"], row["error_kind"]) == ("error", None, "execution")
    assert "Harness crashed in the test." in row["error_reason"]


def test_time_limit_is_an_error(folder, tmp_path):
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, config.modes.plain, "reference", 1)
    task.solver = mock_delay(2)
    task.time_limit = 1
    log = eval(task, fail_on_error=False, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (row["status"], row["passed"], row["error_kind"]) == ("error", None, "time_limit")
    assert row["error_reason"]


def test_choice_target_list_accepts_either_letter(folder, tmp_path):
    (folder / "eval.yaml").write_text("type: quiz\nmotivation: Check accepted alternatives.\nprompt: Select a greeting.\nmodes: [vanilla]\nchoices: [hello, hi, goodbye]\n")
    (folder / "scorer/scorer.yaml").write_text('kind: target\nmethod: choice\ntarget: ["A", "B"]\n')
    config = load_config()
    task = build_task(load_eval(folder, config), config, None, config.modes.plain, "reference", 1)
    task.model = get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", "ANSWER: B")])
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert json.loads(row["checks_json"]) == {"answer": {"passed": True, "reason": "Answer matches the target."}}


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
