import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from inspect_ai import Task, eval
from inspect_ai._eval.task.hf import HFTask, _record_to_sample_hf
from inspect_ai.dataset import json_dataset
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model
import inspect_ai.scorer as scorers
import inspect_ai.solver as solvers

from ethevals.config import load_config
from ethevals.hf import write_hf
from ethevals.loader import load_eval
from ethevals.publish import publish_logs
from ethevals.rows import results_rows
from prove_hf import prove
from support import build_task

ROOT = Path(__file__).resolve().parents[2]


def quiz(tmp_path, name="units", *, modes=None, choices=None, **scorer):
    folder = tmp_path / "concepts" / name
    (folder / "workspace").mkdir(parents=True)
    (folder / "scorer").mkdir()
    (folder / "eval.yaml").write_text(yaml.safe_dump({"type": "quiz", "motivation": "Check units.",
        "prompt": "Give the unit.", "modes": modes or ["vanilla"], "choices": choices}))
    (folder / "scorer/scorer.yaml").write_text(yaml.safe_dump({"scorers": [{"kind": "target", "target": "wei", **scorer}]}))
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
    write_hf([included, excluded], output)
    path = next(output.glob("data/*/test.jsonl"))
    sample = json_dataset(str(path))[0]
    assert (sample.id, sample.input, sample.target, sample.metadata["eval_id"]) == (
        "concepts/units", "Give the unit.", "wei", "concepts/units")
    assert "Dataset license is undecided" in (output / "README.md").read_text()
    with pytest.raises(ValueError, match="empty output directory"):
        write_hf([included], output)


@pytest.mark.parametrize("method,choices,targets", [("match", None, ["wei", "Wei"]),
                                                     ("choice", ["one", "two"], ["A", "B"])])
def test_export_rejects_alternatives_without_partial_files(tmp_path, method, choices, targets):
    good = quiz(tmp_path, "a-good")
    bad = quiz(tmp_path, "z-alternatives", method=method, choices=choices, target=targets)
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
    ({"method": "choice", "choices": ["one", "two"], "target": "B"}, "ANSWER: B", "C"),
    ({"method": "choice", "choices": ["one", "two"], "target": "B"}, "ANSWER: A", "I"),
])
def test_hf_task_matches_runner_for_the_same_answer(tmp_path, settings, answer, expected):
    evaluation = quiz(tmp_path, **settings)
    write_hf([evaluation], tmp_path / "hf")
    spec = HFTask.model_validate(yaml.safe_load((tmp_path / "hf/eval.yaml").read_text())["tasks"][0])
    record = json.loads(next((tmp_path / "hf").glob("data/*/*.jsonl")).read_text())
    model = lambda: get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", answer)])
    task = Task(dataset=[_record_to_sample_hf(record, spec.field_spec)],
                solver=[getattr(solvers, item.name)(**item.args) for item in spec.solvers],
                scorer=[getattr(scorers, item.name)(**item.args) for item in spec.scorers], model=model())
    log = read_eval_log(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0].location)
    assert [score.value for score in log.samples[0].scores.values()] == [expected]
    runner = build_task(evaluation, load_config(), None, "vanilla", "reference", 1)
    runner.model = model()
    rows = results_rows(read_eval_log(eval(runner, log_dir=str(tmp_path / "logs"), display="none")[0].location))
    assert [row["passed"] for row in rows] == [expected == "C"]


def test_hf_proof_covers_every_fixture_task(tmp_path):
    folders = sorted((ROOT / "evals").glob("*/*"))
    write_hf([load_eval(folder, load_config()) for folder in folders], tmp_path / "hf")
    report = prove(tmp_path / "hf", folders, tmp_path / "proof")
    assert sorted((row["eval_id"], row["answer"], row["json_dataset"], row["hf_loader"], row["runner"]) for row in report) == [
        ("concepts/agent-registries", "reference", "C", "C", "C"),
        ("concepts/agent-registries", "wrong", "I", "I", "I"),
        ("concepts/wei-per-ether", "reference", "C", "C", "C"),
        ("concepts/wei-per-ether", "wrong", "I", "I", "I"),
    ]


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
    rows = [{"eval_id": "concepts/units", "model": "mockllm/model", "mode": "vanilla", "epoch": epoch,
             "log_file": "logs/kept.eval"} for epoch in [1, 2]]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def test_publish_dry_run_picks_only_referenced_logs_and_stages_linked_rows(tmp_path):
    rows = local_results(tmp_path)
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "publish-logs", "--output", str(tmp_path),
                             "--repo", "example/ethevals", "--run-id", "123-1", "--target", "a" * 40, "--dry-run"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert (plan["dry_run"], plan["release"]) == (True, "results-123-1")
    assert [(asset["name"], asset["url"], [row["epoch"] for row in asset["rows"]]) for asset in plan["assets"]] == [
        ("kept.eval", "https://github.com/example/ethevals/releases/download/results-123-1/kept.eval", [1, 2])]
    published = [json.loads(line) for line in Path(plan["rows_file"]).read_text().splitlines()]
    assert published == [{**row, "log_file": "results-123-1/kept.eval"} for row in rows]
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
    def failed(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr("ethevals.publish.subprocess.run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        publish_logs(tmp_path, "example/ethevals", "1", "a" * 40, publish=True)
    assert not (tmp_path / "published/rows.jsonl").exists()
    receipt = []
    def succeeded(command, **kwargs):
        receipt.append(command)
        return subprocess.CompletedProcess(command, 0, "release fixture")
    monkeypatch.setattr("ethevals.publish.subprocess.run", succeeded)
    plan = publish_logs(tmp_path, "example/ethevals", "1", "a" * 40, publish=True)
    assert [json.loads(line) for line in Path(plan["rows_file"]).read_text().splitlines()] == [
        {**row, "log_file": "results-1/kept.eval"} for row in rows]
    assert receipt[0][:10] == ["gh", "release", "create", "results-1", "--repo", "example/ethevals",
                               "--target", "a" * 40, "--latest=false", "--title"]
