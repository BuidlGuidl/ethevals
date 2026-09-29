from pathlib import Path
import json
import subprocess
import sys

from ethevals.hf import write_hf
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from inspect_ai._eval.task import hf
from inspect_ai import eval
from inspect_ai.dataset import json_dataset
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model
import pytest
import yaml

from support import build_task, fixture_config, fixture_quiz


def local_hf_tasks(export: Path):
    """Replace only Hub I/O and its dependency check; keep Inspect's task creation."""
    card = yaml.safe_load((export / "README.md").read_text().split("---", 2)[1])
    paths = {item["config_name"]: export / item["data_files"][0]["path"] for item in card["configs"]}

    def download(*, repo_id, filename, repo_type, revision):
        if filename != "eval.yaml" or repo_type != "dataset":
            raise ValueError(f"Unexpected HF download: {filename}")
        return str(export / filename)

    def dataset(*, path, revision, name, split, sample_fields):
        if split != "test":
            raise ValueError(f"Unexpected HF split: {split}")
        return json_dataset(str(paths[name]), sample_fields=sample_fields)

    hub = ModuleType("huggingface_hub")
    hub.hf_hub_download = download
    hub.errors = SimpleNamespace(EntryNotFoundError=FileNotFoundError)
    with patch.dict("sys.modules", {"huggingface_hub": hub}), \
            patch.object(hf, "verify_required_version"), patch.object(hf, "hf_dataset", dataset):
        return hf.task_create_from_hf("hf/local/ethevals")


def test_hf_cli_exports_fixture_rows_card_and_benchmark(tmp_path, config_path):
    evals = [fixture_quiz(tmp_path, "unit"), fixture_quiz(tmp_path, "choice", choices=["wei", "ether"], target="A"),
             fixture_quiz(tmp_path, "agent-only", modes=["internet"])]
    rubric = fixture_quiz(tmp_path, "rubric")
    (rubric.folder / "scorer/rubric.md").write_text("## explained\nDid the answer explain the unit?\n")
    evals.append(load_eval(rubric.folder, fixture_config()))
    output = tmp_path / "hf"
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "export-hf", "--output", str(output),
                             "--hf-repo", "example/ethereum", "--license", "cc-by-4.0",
                             "--config", str(config_path), "--evals", *[str(item.folder) for item in evals]], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["rows"] == 2
    assert json.loads(result.stdout)["skipped"] == [
        {"eval_id": "concepts/agent-only", "reason": "vanilla mode is not declared"},
        {"eval_id": "concepts/rubric", "reason": "rubric cannot be exported"}]
    samples = [sample for path in output.glob("data/*/test.jsonl") for sample in json_dataset(str(path))]
    assert sorted((sample.id, sample.input, sample.target, sample.choices) for sample in samples) == [
        ("concepts/choice", "Give the unit.", "A", ["wei", "ether"]),
        ("concepts/unit", "Give the unit.", "wei", None)]
    with pytest.raises(ValueError):
        write_hf(evals, output)


def test_export_rejects_alternatives_without_partial_files(tmp_path):
    good = fixture_quiz(tmp_path, "a-good")
    bad = fixture_quiz(tmp_path, "z-alternatives", modes=["internet"], target=['wei', 'Wei'])
    bad.declaration.modes = ["vanilla"]
    with pytest.raises(ValueError, match="cannot preserve alternative targets"):
        write_hf([good, bad], tmp_path / "hf")
    assert not (tmp_path / "hf").exists()
    write_hf([good], tmp_path / "hf")
    assert json_dataset(str(next((tmp_path / "hf").glob("data/*/*.jsonl"))))[0].target == "wei"


@pytest.mark.parametrize("settings,answer,expected", [
    ({}, "The answer is wei", "I"),
    ({"location": "end"}, "The answer is wei", "C"),
    ({"method": "pattern", "pattern": r"Unit: (\w+)"}, "Unit: wei", "C"),
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


def test_configs_separate_scorer_options_and_group_matching_options(tmp_path):
    evals = [fixture_quiz(tmp_path, "exact"), fixture_quiz(tmp_path, "also-exact"), fixture_quiz(tmp_path, "end", location="end")]
    write_hf(evals, tmp_path / "hf")
    tasks = yaml.safe_load((tmp_path / "hf/eval.yaml").read_text())["tasks"]
    grouped = {}
    for spec in tasks:
        grouped[spec["scorers"][0]["args"]["location"]] = [
            sample.id for sample in json_dataset(str(tmp_path / "hf/data" / spec["config"] / "test.jsonl"))]
    assert grouped == {"exact": ["concepts/also-exact", "concepts/exact"], "end": ["concepts/end"]}


def test_blank_choice_fails_at_load(tmp_path):
    with pytest.raises(ValueError, match="choices.*blank"):
        fixture_quiz(tmp_path, choices=["wei", " \t", "ether"], target="C")
