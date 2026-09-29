from pathlib import Path
import json

from ethevals.loader import load_eval
from ethevals.rows import results_rows
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model
import pytest

from support import build_task, eval_cli, fixture_config, run


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("answer,expected", [("reference", True), ("empty", False)])
def test_quizzes_through_real_pipeline(tmp_path, answer, expected):
    config = fixture_config()
    evals = [load_eval(path, config) for path in sorted((ROOT / "evals").glob("*/*"))]
    evals = [item for item in evals if item.declaration.type == "quiz" and "vanilla" in item.declaration.modes]
    output = tmp_path / answer
    success, rows = run(evals, config, output, answer=answer)
    assert success is True
    assert [(row["eval_id"], row["epoch"], (None if row["status"] == "error" else row["status"] == "passed")) for row in rows] == [
        (item.id, epoch, expected) for item in evals for epoch in range(1, config.epochs + 1)
    ]
    assert [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()] == rows
    for row in rows:
        check_name = next(item.target.name for item in evals if item.id == row["eval_id"])
        reason = "Answer matches the target." if expected else "The answer is empty." if answer == "empty" else "Answer does not match the target."
        assert row["checks"] == {check_name: {"passed": expected, "reason": reason}}
        assert (row["model_cost_usd"], row["cost_source"]) == (0.0, "mock")
        assert Path(row["log_file"]).is_absolute() is False
        log = read_eval_log(output / row["log_file"])
        sample = log.samples[0]
        assert sample.id == row["eval_id"]
        calls = [event for event in sample.events if event.event == "model"]
        assert len(calls) == 1
        assert calls[0].tools == []


@pytest.mark.parametrize("method,answer,expected", [("pattern", "ERC 8004", True), ("pattern", "ERC 20", False), ("match", "20", False)])
def test_target_methods_from_real_log(folder, tmp_path, method, answer, expected):
    path = folder / "scorer/target.yaml"
    path.write_text('name: number\ntarget: "8004"\nmethod: ' + method + ('\npattern: "ERC ([0-9]+)"\n' if method == "pattern" else "\n"))
    config = fixture_config()
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    task.model = get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert (None if row["status"] == "error" else row["status"] == "passed") is expected
    assert row["checks"]["number"]["passed"] is expected


def test_choice_target_list_accepts_either_letter(folder, tmp_path):
    (folder / "eval.yaml").write_text("type: quiz\nmotivation: Check accepted alternatives.\nprompt: Select a greeting.\nmodes: [internet]\nchoices: [hello, hi, goodbye]\n")
    (folder / "scorer/target.yaml").write_text('target: ["A", "B"]\n')
    config = fixture_config()
    task = build_task(load_eval(folder, config), config, None, "internet", "reference", 1)
    task.model = get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", "ANSWER: B")])
    task.dataset[0].sandbox = task.dataset[0].files = None
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(read_eval_log(log.location))[0]
    assert row["checks"] == {"answer": {"passed": True, "reason": "Answer matches the target."}}


@pytest.mark.parametrize("pattern,reference", [("ERC ([0-9]+)", "ERC 8004"), ("ERC-?([0-9]+)", "ERC-8004")])
def test_pattern_check_through_cli(folder, tmp_path, pattern, reference):
    (folder / "scorer/target.yaml").write_text(
        f'target: "8004"\nmethod: pattern\npattern: "{pattern}"\nreference: "{reference}"\n'
    )
    output = tmp_path / "results"
    for invocation in range(2):
        if invocation:
            path = folder / "eval.yaml"
            path.write_text(path.read_text() + "\n# Author edited the eval.\n")
        result = eval_cli("check", "--evals", folder, "--epochs", 1, "--output", output)
        assert result.returncode == 0, result.stdout + result.stderr
        reference_rows = [json.loads(line) for line in (output / "reference/rows.jsonl").read_text().splitlines()]
        empty_rows = [json.loads(line) for line in (output / "empty/rows.jsonl").read_text().splitlines()]
        assert [row["status"] for row in reference_rows] == ["passed"] * (invocation + 1)
        assert [row["status"] for row in empty_rows] == ["failed"] * (invocation + 1)
    assert len(list((output / "reference/logs").rglob("*.eval"))) == 2
