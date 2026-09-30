from pathlib import Path
import json

from ethevals.loader import load_eval
from ethevals.rows import results_rows
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model
import pytest

from support import build_task, fixture_config, run


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
