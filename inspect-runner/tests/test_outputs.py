import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval
from inspect_ai._eval.task.hf import HFTask
from inspect_ai.dataset import json_dataset
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model

from support import load_config
from ethevals.hf import write_hf
from ethevals.loader import load_eval
from ethevals.publish import publish_logs
from ethevals.rows import results_rows
from hf_proof import local_hf_tasks, prove
from support import build_task

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = load_eval(ROOT / "evals/concepts/agent-registries", load_config())


def quiz(tmp_path, name="units", *, modes=None, choices=None, **scorer):
    folder = tmp_path / "concepts" / name
    (folder / "workspace").mkdir(parents=True)
    (folder / "scorer").mkdir()
    (folder / "eval.yaml").write_text(yaml.safe_dump({"type": "quiz", "motivation": "Check units.",
        "prompt": "Give the unit.", "modes": modes or ["vanilla"], "choices": choices}))
    (folder / "scorer/target.yaml").write_text(yaml.safe_dump({"target": "wei", **scorer}))
    return load_eval(folder, load_config())


def test_hf_cli_exports_fixture_rows_card_and_benchmark(tmp_path):
    output = tmp_path / "hf"
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "export-hf", "--output", str(output),
                             "--hf-repo", "example/ethereum", "--license", "cc-by-4.0"], capture_output=True, text=True)
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
            assert sample.metadata["eval_hash"] == load_eval(ROOT / "evals" / sample.id, load_config()).hash
    assert observed == {
        "concepts/agent-registries": ("8004", None, "concepts", "generate", "match",
                                     {"location": "exact", "ignore_case": True, "numeric": False}),
        "concepts/wei-per-ether": ("C", ["10^6", "10^9", "10^18", "10^24"], "concepts", "multiple_choice", "choice", {}),
    }
    assert sorted(path.suffix for path in output.rglob("*") if path.is_file()) == [".jsonl", ".jsonl", ".md", ".yaml"]


def test_export_selects_vanilla_quizzes_and_keeps_prompts(tmp_path):
    included = quiz(tmp_path, target=["wei"])
    excluded = quiz(tmp_path, "agent-only", modes=["internet"])
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
    good = quiz(tmp_path, "a-good")
    bad = quiz(tmp_path, "z-alternatives", modes=["internet"], choices=choices, target=targets)
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
    evaluation = quiz(tmp_path, **settings)
    write_hf([evaluation], tmp_path / "hf")
    model = lambda: get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])
    task = local_hf_tasks(tmp_path / "hf")[0]
    task.model = model()
    log = read_eval_log(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0].location)
    assert [score.value for score in log.samples[0].scores.values()] == [expected]
    runner = build_task(evaluation, load_config(), None, "vanilla", "reference", 1)
    runner.model = model()
    rows = results_rows(read_eval_log(eval(runner, log_dir=str(tmp_path / "logs"), display="none")[0].location))
    assert [(None if row["status"] == "error" else row["status"] == "passed") for row in rows] == [expected == "C"]


def test_hf_proof_covers_every_fixture_task(tmp_path):
    folders = sorted((ROOT / "evals").glob("*/*"))
    write_hf([load_eval(folder, load_config()) for folder in folders], tmp_path / "hf")
    report = prove(tmp_path / "hf", [load_eval(folder, load_config()) for folder in folders], tmp_path / "proof", load_config())
    assert json.loads((tmp_path / "proof/report.json").read_text()) == report
    assert sorted((row["eval_id"], row["answer"], row["json_dataset"], row["hf_loader"], row["runner"]) for row in report) == [
        ("concepts/agent-registries", "reference", "C", "C", "C"),
        ("concepts/agent-registries", "wrong", "I", "I", "I"),
        ("concepts/wei-per-ether", "reference", "C", "C", "C"),
        ("concepts/wei-per-ether", "wrong", "I", "I", "I"),
    ]


def test_changing_fixture_scorer_updates_runner_and_export(tmp_path):
    evaluation = quiz(tmp_path)
    path = evaluation.folder / "scorer/target.yaml"
    for location, verdict, passed in [("exact", "I", False), ("end", "C", True)]:
        settings = yaml.safe_load(path.read_text())
        settings["location"] = location
        path.write_text(yaml.safe_dump(settings))
        evaluation = load_eval(evaluation.folder, load_config())
        output = tmp_path / location
        write_hf([evaluation], output)
        spec = yaml.safe_load((output / "eval.yaml").read_text())["tasks"][0]
        assert spec["scorers"] == [{"name": "match", "args": {
            "location": location, "ignore_case": True, "numeric": False}}]
        assert spec["solvers"] == [{"name": "generate", "args": {}}]
        exported = local_hf_tasks(output)[0]
        runner = build_task(evaluation, load_config(), None, "vanilla", "reference", 1)
        for task in (exported, runner):
            task.model = get_model("mockllm/model", custom_outputs=[
                ModelOutput.from_content("mockllm/model", "The unit is wei")])
        exported_log = eval(exported, log_dir=str(tmp_path / "logs"), display="none")[0]
        assert [score.value for score in exported_log.samples[0].scores.values()] == [verdict]
        runner_log = eval(runner, log_dir=str(tmp_path / "logs"), display="none")[0]
        assert [(row["status"], (None if row["status"] == "error" else row["status"] == "passed")) for row in results_rows(runner_log)] == [
            ("passed" if passed else "failed", passed)]


def test_configs_separate_scorer_options_and_group_matching_options(tmp_path):
    evals = [quiz(tmp_path, "exact"), quiz(tmp_path, "also-exact"), quiz(tmp_path, "end", location="end")]
    write_hf(evals, tmp_path / "hf")
    tasks = yaml.safe_load((tmp_path / "hf/eval.yaml").read_text())["tasks"]
    grouped = {}
    for spec in tasks:
        grouped[spec["scorers"][0]["args"]["location"]] = [
            sample.id for sample in json_dataset(str(tmp_path / "hf/data" / spec["config"] / "test.jsonl"))]
    assert grouped == {"exact": ["concepts/also-exact", "concepts/exact"], "end": ["concepts/end"]}


def local_results(tmp_path):
    (tmp_path / "logs").mkdir()
    for name in ["old.eval", "kept.eval", "unused.eval"]:
        (tmp_path / "logs" / name).write_bytes(b"log fixture")
    rows = [{"eval_id": EVALUATION.id, "eval_hash": EVALUATION.hash,
             "status": "passed", "model": "test/model", "mode": "vanilla", "epoch": epoch,
             "log_file": "logs/kept.eval"} for epoch in [1, 2]]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def test_publish_dry_run_picks_only_referenced_logs_and_writes_nothing(tmp_path):
    rows = local_results(tmp_path)
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "publish-logs", "--output", str(tmp_path),
                             "--repo", "example/ethevals", "--run-id", "123-1", "--commit", "a" * 40],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert (plan["dry_run"], plan["release"]) == (True, "results-123-1")
    assert [(asset["name"], asset["url"], [row["epoch"] for row in asset["rows"]]) for asset in plan["assets"]] == [
        ("kept.eval", "https://github.com/example/ethevals/releases/download/results-123-1/kept.eval", [1, 2])]
    assert not (tmp_path / "published").exists()
    assert [json.loads(line) for line in (tmp_path / "rows.jsonl").read_text().splitlines()] == rows
    assert plan["command"][:4] == ["gh", "release", "create", "results-123-1"]
    assert plan["command"][-1] == str(tmp_path / "logs/kept.eval")


@pytest.mark.parametrize("file", ["../secret.eval", "/secret.eval", "logs/missing.eval", "logs/bad name.eval"])
def test_publish_rejects_missing_or_unsafe_logs(tmp_path, file):
    rows = local_results(tmp_path)
    rows[0]["log_file"] = file
    (tmp_path / "rows.jsonl").write_text(json.dumps(rows[0]) + "\n")
    with pytest.raises(ValueError, match="row 1:"):
        publish_logs(tmp_path, "example/ethevals", "1", "a" * 40)
    (tmp_path / "rows.jsonl").write_text(json.dumps(rows[1]) + "\n")
    assert publish_logs(tmp_path, "example/ethevals", "1", "a" * 40)["assets"][0]["name"] == "kept.eval"


def test_publish_stages_rows_only_after_the_release_command_succeeds(tmp_path, monkeypatch):
    rows = local_results(tmp_path)
    dry = publish_logs(tmp_path, "example/ethevals", "dry", "a" * 40)
    assert dry["release"] == "results-dry"
    def failed(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr("ethevals.publish.subprocess.run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        publish_logs(tmp_path, "example/ethevals", "1", "a" * 40, publish=True)
    assert not list((tmp_path / "published").glob("*.jsonl"))
    receipt = []
    def succeeded(command, **kwargs):
        receipt.append(command)
        return subprocess.CompletedProcess(command, 0, "release fixture")
    monkeypatch.setattr("ethevals.publish.subprocess.run", succeeded)
    plan = publish_logs(tmp_path, "example/ethevals", "1", "a" * 40, publish=True)
    assert Path(plan["rows_file"]).name == "results-1.jsonl"
    assert [json.loads(line) for line in Path(plan["rows_file"]).read_text().splitlines()] == [
        {**row, "log_url": "https://github.com/example/ethevals/releases/download/results-1/kept.eval"} for row in rows]
    assert receipt[0][:10] == ["gh", "release", "create", "results-1", "--repo", "example/ethevals",
                               "--target", "a" * 40, "--latest=false", "--title"]


@pytest.mark.parametrize("blank", ["", " \t"])
def test_blank_choice_fails_at_load(tmp_path, blank):
    with pytest.raises(ValueError, match="choices.*blank"):
        quiz(tmp_path, choices=["wei", blank, "ether"], target="C")


def test_hash_in_output_path_cannot_select_an_unrelated_file(tmp_path):
    (tmp_path / "job").write_text("unrelated private file")
    output = tmp_path / "job#1"
    output.mkdir()
    local_results(output)
    with pytest.raises(ValueError, match="#"):
        publish_logs(output, "example/ethevals", "1", "a" * 40)


def test_reused_folder_skips_published_and_hidden_rows(tmp_path, monkeypatch):
    rows = local_results(tmp_path)
    monkeypatch.setattr("ethevals.publish.subprocess.run", lambda *args, **kwargs: None)
    publish_logs(tmp_path, "example/ethevals", "first", "a" * 40, publish=True)
    (tmp_path / "logs/new.eval").write_bytes(b"new log")
    rows += [{**rows[0], "epoch": epoch, **change} for epoch, change in enumerate([
        {"log_url": "https://github.com/example/ethevals/releases/download/results-elsewhere/linked.eval"},
        {"eval_hash": "old", "log_file": "logs/new.eval"},
        {"mode": "skills", "log_file": "logs/new.eval"},
        {"log_file": "logs/new.eval"},
    ], 3)]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    plan = publish_logs(tmp_path, "example/ethevals", "second", "a" * 40)
    assert [(asset["name"], [row["epoch"] for row in asset["rows"]]) for asset in plan["assets"]] == [("new.eval", [4, 5, 6])]
    assert plan["skipped"] == {"published": 3}
    assert sorted(path.name for path in (tmp_path / "published").iterdir()) == ["results-first.jsonl"]


@pytest.mark.parametrize("unsupported", ["alternatives", "second-scorer"])
def test_validate_rejects_unexportable_vanilla_quiz(tmp_path, unsupported):
    evaluation = quiz(tmp_path, modes=["internet"])
    path = evaluation.folder / "scorer/target.yaml"
    target = {"target": ["wei", "ether"] if unsupported == "alternatives" else "wei"}
    if unsupported == "second-scorer":
        (evaluation.folder / "scorer/rubric.md").write_text("## unit\nIs the unit correct?\n")
    path.write_text(yaml.safe_dump(target))
    declaration = evaluation.declaration.model_dump()
    declaration["modes"] = ["vanilla"]
    (evaluation.folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "validate", "--evals", str(evaluation.folder)],
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
    write_hf([quiz(tmp_path, "exact"), quiz(tmp_path, "end", location="end")], tmp_path / "hf")
    tasks = local_hf_tasks(tmp_path / "hf", "concepts-match-end")
    assert [[sample.metadata["metadata"]["eval_id"] for sample in task.dataset] for task in tasks] == [["concepts/end"]]
    with pytest.raises(Exception, match="No tasks matching"):
        local_hf_tasks(tmp_path / "hf", "missing")


def test_proof_records_observed_verdicts_before_reporting_mismatch(tmp_path, monkeypatch):
    evaluation = quiz(tmp_path)
    write_hf([evaluation], tmp_path / "hf")
    monkeypatch.setattr("hf_proof.target_reference", lambda *args: "wrong unit")
    with pytest.raises(ValueError, match="HF parity mismatch"):
        prove(tmp_path / "hf", [evaluation], tmp_path / "proof", load_config())
    report = json.loads((tmp_path / "proof/report.json").read_text())
    assert [(row["answer"], row["json_dataset"], row["hf_loader"], row["runner"]) for row in report] == [
        ("reference", "I", "I", "I"), ("wrong", "I", "I", "I")]


def test_dataset_card_size_uses_exported_row_count(tmp_path):
    evaluation = quiz(tmp_path)
    result = write_hf([evaluation] * 1000, tmp_path / "hf")
    card = yaml.safe_load((tmp_path / "hf/README.md").read_text().split("---", 2)[1])
    assert (result["rows"], card["size_categories"]) == (1000, ["1K<n<10K"])
