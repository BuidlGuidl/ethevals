from pathlib import Path
import json
import subprocess
import sys

from ethevals.hf import write_hf
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from hf_proof import local_hf_tasks, prove
from inspect_ai import eval
from inspect_ai._eval.task.hf import HFTask
from inspect_ai.dataset import json_dataset
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model
import pytest
import yaml

from conftest import fixture_config, fixture_quiz
from support import build_task



def test_hf_cli_exports_fixture_rows_card_and_benchmark(tmp_path, config_path):
    evals = [fixture_quiz(tmp_path, "unit"), fixture_quiz(tmp_path, "choice", choices=["wei", "ether"], target="A")]
    output = tmp_path / "hf"
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "export-hf", "--output", str(output),
                             "--hf-repo", "example/ethereum", "--license", "cc-by-4.0",
                             "--config", str(config_path), "--evals", *[str(item.folder) for item in evals]], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["rows"] == 2
    text = (output / "README.md").read_text()
    card = yaml.safe_load(text.split("---", 2)[1])
    assert card["license"] == "cc-by-4.0"
    assert [(item["config_name"], item.get("default", False)) for item in card["configs"]] == [
        ("concepts-choice", True), ("concepts-match-exact", False)]
    assert 'hf_dataset("example/ethereum", name=' in text
    assert "inspect eval hf/example/ethereum" in text
    tasks = yaml.safe_load((output / "eval.yaml").read_text())["tasks"]
    observed = {}
    for item in card["configs"]:
        spec = HFTask.model_validate(next(task for task in tasks if task["config"] == item["config_name"]))
        dataset = json_dataset(str(output / item["data_files"][0]["path"]))
        for sample in dataset:
            observed[sample.id] = (sample.target, sample.choices, sample.metadata["pillar"],
                                   spec.solvers[0].name, spec.scorers[0].name, spec.scorers[0].args)
            assert sample.metadata["eval_hash"] == next(item.hash for item in evals if item.id == sample.id)
    assert observed == {
        "concepts/unit": ("wei", None, "concepts", "generate", "match",
                                     {"location": "exact", "ignore_case": True, "numeric": False}),
        "concepts/choice": ("A", ["wei", "ether"], "concepts", "multiple_choice", "choice", {}),
    }
    assert sorted(path.suffix for path in output.rglob("*") if path.is_file()) == [".jsonl", ".jsonl", ".md", ".yaml"]


def test_export_selects_vanilla_quizzes_and_keeps_prompts(tmp_path):
    included = fixture_quiz(tmp_path, target=["wei"])
    excluded = fixture_quiz(tmp_path, "agent-only", modes=["internet"])
    output = tmp_path / "hf"
    result = write_hf([included, excluded], output)
    assert result["skipped"] == [{"eval_id": "concepts/agent-only", "reason": "vanilla mode is not declared"}]
    path = next(output.glob("data/*/test.jsonl"))
    sample = json_dataset(str(path))[0]
    assert (sample.id, sample.input, sample.target, sample.metadata["eval_id"]) == (
        "concepts/units", "Give the unit.", "wei", "concepts/units")
    assert "Dataset license is undecided" in (output / "README.md").read_text()
    with pytest.raises(ValueError, match="empty output directory"):
        write_hf([included], output)


@pytest.mark.parametrize("choices,targets", [(None, ["wei", "Wei"]), (["one", "two"], ["A", "B"])])
def test_export_rejects_alternatives_without_partial_files(tmp_path, choices, targets):
    good = fixture_quiz(tmp_path, "a-good")
    bad = fixture_quiz(tmp_path, "z-alternatives", modes=["internet"], choices=choices, target=targets)
    bad.declaration.modes = ["vanilla"]
    with pytest.raises(ValueError, match="cannot preserve alternative targets"):
        write_hf([good, bad], tmp_path / "hf")
    assert not (tmp_path / "hf").exists()
    write_hf([good], tmp_path / "hf")
    assert json_dataset(str(next((tmp_path / "hf").glob("data/*/*.jsonl"))))[0].target == "wei"


@pytest.mark.parametrize("settings,answer,expected", [
    ({}, "The answer is wei", "I"),
    ({"location": "end"}, "The answer is wei", "C"),
    ({"location": "begin"}, "wei is the unit", "C"),
    ({"location": "any"}, "one wei here", "C"),
    ({"ignore_case": False}, "WEI", "I"),
    ({"numeric": True, "target": "1000"}, "1,000", "C"),
    ({"method": "pattern", "pattern": r"Unit: (\w+)"}, "Unit: wei", "C"),
    ({"method": "pattern", "pattern": r"Unit: (\w+)"}, "Unit: ether", "I"),
    ({"choices": ["one", "two"], "target": "B"}, "ANSWER: B", "C"),
    ({"choices": ["one", "two"], "target": "B"}, "ANSWER: A", "I"),
])
def test_hf_task_matches_runner_for_the_same_answer(tmp_path, settings, answer, expected):
    evaluation = fixture_quiz(tmp_path, **settings)
    write_hf([evaluation], tmp_path / "hf")
    model = lambda: get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])
    task = local_hf_tasks(tmp_path / "hf")[0]
    task.model = model()
    log = read_eval_log(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0].location)
    assert [score.value for score in log.samples[0].scores.values()] == [expected]
    runner = build_task(evaluation, fixture_config(), None, "vanilla", "reference", 1)
    runner.model = model()
    rows = results_rows(read_eval_log(eval(runner, log_dir=str(tmp_path / "logs"), display="none")[0].location))
    assert [(None if row["status"] == "error" else row["status"] == "passed") for row in rows] == [expected == "C"]


def test_hf_proof_covers_every_fixture_task(tmp_path):
    evals = [fixture_quiz(tmp_path, "unit"), fixture_quiz(tmp_path, "choice", choices=["wei", "ether"], target="A")]
    write_hf(evals, tmp_path / "hf")
    report = prove(tmp_path / "hf", evals, tmp_path / "proof", fixture_config())
    assert json.loads((tmp_path / "proof/report.json").read_text()) == report
    assert sorted((row["eval_id"], row["answer"], row["json_dataset"], row["hf_loader"], row["runner"]) for row in report) == [
        ("concepts/choice", "reference", "C", "C", "C"),
        ("concepts/choice", "wrong", "I", "I", "I"),
        ("concepts/unit", "reference", "C", "C", "C"),
        ("concepts/unit", "wrong", "I", "I", "I"),
    ]


def test_changing_fixture_scorer_updates_runner_and_export(tmp_path):
    evaluation = fixture_quiz(tmp_path)
    path = evaluation.folder / "scorer/target.yaml"
    for location, verdict, passed in [("exact", "I", False), ("end", "C", True)]:
        settings = yaml.safe_load(path.read_text())
        settings["location"] = location
        path.write_text(yaml.safe_dump(settings))
        evaluation = load_eval(evaluation.folder, fixture_config())
        output = tmp_path / location
        write_hf([evaluation], output)
        spec = yaml.safe_load((output / "eval.yaml").read_text())["tasks"][0]
        assert spec["scorers"] == [{"name": "match", "args": {
            "location": location, "ignore_case": True, "numeric": False}}]
        assert spec["solvers"] == [{"name": "generate", "args": {}}]
        exported = local_hf_tasks(output)[0]
        runner = build_task(evaluation, fixture_config(), None, "vanilla", "reference", 1)
        for task in (exported, runner):
            task.model = get_model("mockllm/model", custom_outputs=[
                ModelOutput.from_content("mockllm/model", "The unit is wei")])
        exported_log = eval(exported, log_dir=str(tmp_path / "logs"), display="none")[0]
        assert [score.value for score in exported_log.samples[0].scores.values()] == [verdict]
        runner_log = eval(runner, log_dir=str(tmp_path / "logs"), display="none")[0]
        assert [(row["status"], (None if row["status"] == "error" else row["status"] == "passed")) for row in results_rows(runner_log)] == [
            ("passed" if passed else "failed", passed)]


def test_configs_separate_scorer_options_and_group_matching_options(tmp_path):
    evals = [fixture_quiz(tmp_path, "exact"), fixture_quiz(tmp_path, "also-exact"), fixture_quiz(tmp_path, "end", location="end")]
    write_hf(evals, tmp_path / "hf")
    tasks = yaml.safe_load((tmp_path / "hf/eval.yaml").read_text())["tasks"]
    grouped = {}
    for spec in tasks:
        grouped[spec["scorers"][0]["args"]["location"]] = [
            sample.id for sample in json_dataset(str(tmp_path / "hf/data" / spec["config"] / "test.jsonl"))]
    assert grouped == {"exact": ["concepts/also-exact", "concepts/exact"], "end": ["concepts/end"]}


@pytest.mark.parametrize("blank", ["", " \t"])
def test_blank_choice_fails_at_load(tmp_path, blank):
    with pytest.raises(ValueError, match="choices.*blank"):
        fixture_quiz(tmp_path, choices=["wei", blank, "ether"], target="C")


@pytest.mark.parametrize("unsupported", ["alternatives", "second-scorer"])
def test_validate_rejects_unexportable_vanilla_quiz(tmp_path, unsupported, config_path):
    evaluation = fixture_quiz(tmp_path, modes=["internet"])
    path = evaluation.folder / "scorer/target.yaml"
    target = {"target": ["wei", "ether"] if unsupported == "alternatives" else "wei"}
    if unsupported == "second-scorer":
        (evaluation.folder / "scorer/rubric.md").write_text("## unit\nIs the unit correct?\n")
    path.write_text(yaml.safe_dump(target))
    declaration = evaluation.declaration.model_dump()
    declaration["modes"] = ["vanilla"]
    (evaluation.folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "validate", "--evals", str(evaluation.folder), "--config", str(config_path)],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert ("cannot preserve alternative targets" if unsupported == "alternatives" else "scorer files do not match type quiz") in result.stderr


@pytest.mark.parametrize("args", [["run", "--publish"], ["check", "--publish"], ["export-hf"],
                                  ["publish-logs", "--output", "results"]])
def test_cli_rejects_wrong_or_missing_flags(args):
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr or "required" in result.stderr


def test_stock_hf_loader_selects_task_by_id(tmp_path):
    write_hf([fixture_quiz(tmp_path, "exact"), fixture_quiz(tmp_path, "end", location="end")], tmp_path / "hf")
    tasks = local_hf_tasks(tmp_path / "hf", "concepts-match-end")
    assert [[sample.metadata["metadata"]["eval_id"] for sample in task.dataset] for task in tasks] == [["concepts/end"]]
    with pytest.raises(Exception, match="No tasks matching"):
        local_hf_tasks(tmp_path / "hf", "missing")


def test_proof_records_observed_verdicts_before_reporting_mismatch(tmp_path, monkeypatch):
    evaluation = fixture_quiz(tmp_path)
    write_hf([evaluation], tmp_path / "hf")
    monkeypatch.setattr("hf_proof.target_reference", lambda *args: "wrong unit")
    with pytest.raises(ValueError, match="HF parity mismatch"):
        prove(tmp_path / "hf", [evaluation], tmp_path / "proof", fixture_config())
    report = json.loads((tmp_path / "proof/report.json").read_text())
    assert [(row["answer"], row["json_dataset"], row["hf_loader"], row["runner"]) for row in report] == [
        ("reference", "I", "I", "I"), ("wrong", "I", "I", "I")]


def test_dataset_card_size_uses_exported_row_count(tmp_path):
    evaluation = fixture_quiz(tmp_path)
    result = write_hf([evaluation] * 1000, tmp_path / "hf")
    card = yaml.safe_load((tmp_path / "hf/README.md").read_text().split("---", 2)[1])
    assert (result["rows"], card["size_categories"]) == (1000, ["1K<n<10K"])
