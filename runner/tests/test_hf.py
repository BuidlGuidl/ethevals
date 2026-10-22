import json
from pathlib import Path
import shutil

from harbor.models.registry import Registry
from harbor.models.task.task import Task
import pytest
import yaml

from ethevals.cli import main
from ethevals.hf import write_hf
from support import cli


ROOT = Path(__file__).resolve().parents[2]


def test_editor_files_change_neither_task_identity_nor_export(tmp_path):
    from harbor.publisher.packager import Packager
    from ethevals.jobs import task_entry

    task = tmp_path / "concepts/question"
    shutil.copytree(ROOT / "runner/tests/fixtures/harbor/concepts/question", task)
    before = task_entry(task)["hash"]
    write_hf([task], tmp_path / "before")
    (task / "environment/editor.swp").write_text("Unfinished edit.")
    (task / "notes.txt").write_text("Outside the package.")
    write_hf([task], tmp_path / "after")
    assert task_entry(task)["hash"] == before
    files = lambda root: {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert files(tmp_path / "before") == files(tmp_path / "after")
    published = tmp_path / "after/tasks/concepts--question"
    assert set(files(published)) == {p.relative_to(task.resolve()) for p in Packager.collect_files(task)}
    assert "sha256:" + Packager.compute_content_hash(published)[0] == before


def test_export_copies_a_complete_task_and_writes_a_harbor_registry(tmp_path, capsys):
    task = tmp_path / "concepts/question"
    shutil.copytree(ROOT / "runner/tests/fixtures/harbor/concepts/question", task)
    output = tmp_path / "dataset"
    assert main(["export-hf", "--tasks", str(task), "--output", str(output),
                 "--hf-repo", "example/tasks", "--license", "mit"]) == 0
    assert json.loads(capsys.readouterr().out)["tasks"] == 1
    published = output / "tasks/concepts--question"
    assert {p.relative_to(published): p.read_bytes() for p in published.rglob("*") if p.is_file()} == {
        p.relative_to(task): p.read_bytes() for p in task.rglob("*") if p.is_file()}
    registry = Registry.from_path(output / "registry.json")
    assert [(d.name, d.version, [(t.name, str(t.path), t.git_url) for t in d.tasks])
            for d in registry.datasets] == [
        ("ethevals", "1.0", [("buidlguidl/question", "tasks/concepts--question", None)])]
    assert Task(task).name == Task(published).name == "buidlguidl/question"
    assert yaml.safe_load((output / "eval.yaml").read_text()) == {
        "name": "ETH Evals", "description": "Tasks that measure how well AI agents do Ethereum work and what bare models know about Ethereum.",
        "evaluation_framework": "harbor", "tasks": [{"id": "ethevals", "config": "default", "split": "test"}]}
    dataset = json.loads((output / "registry.json").read_text())[0]
    assert (dataset["description"], dataset["version"]) == (
        "Tasks that measure how well AI agents do Ethereum work and what bare models know about Ethereum.", "1.0")
    card = yaml.safe_load((output / "README.md").read_text().split("---", 2)[1])
    assert card["tags"] == ["ethereum", "rl-environment", "harbor"]
    assert card["license"] == "mit"
    assert "harbor run --repo https://huggingface.co/datasets/example/tasks" in (output / "README.md").read_text()
    assert not (output / "data").exists()
    with pytest.raises(ValueError, match="empty output directory"):
        write_hf([task], output)


def test_export_rejects_a_task_with_an_external_build_context_before_copying(tmp_path):
    task = tmp_path / "concepts/question"
    shutil.copytree(ROOT / "runner/tests/fixtures/harbor/concepts/question", task)
    (task / "environment/docker-compose.yaml").write_text(
        "services:\n  main:\n    build: ../../shared\n")
    output = tmp_path / "dataset"
    with pytest.raises(ValueError, match="inside the task folder"):
        write_hf([task], output)
    assert not output.exists()


def test_export_card_lists_host_variables_declared_only_in_compose(tmp_path):
    task = tmp_path / "concepts/question"
    shutil.copytree(ROOT / "runner/tests/fixtures/harbor/concepts/question", task)
    (task / "environment/docker-compose.yaml").write_text(
        "services:\n  browser:\n    environment:\n      URL: ${ARCHIVE_RPC_URL:?Set ARCHIVE_RPC_URL}\n")
    output = tmp_path / "dataset"
    write_hf([task], output)
    card = (output / "README.md").read_text()
    assert "- `buidlguidl/question`: `ARCHIVE_RPC_URL`" in card
    assert "Compose stops with the message if a value is missing or empty." in card


@pytest.mark.docker
def test_exported_package_keeps_its_name_in_a_plain_harbor_trial(tmp_path):
    from ethevals.jobs import task_entry
    task = tmp_path / "concepts/question"
    shutil.copytree(ROOT / "runner/tests/fixtures/harbor/concepts/question", task)
    output = tmp_path / "dataset"
    write_hf([task], output)
    entry = json.loads((output / "registry.json").read_text())[0]["tasks"][0]
    result = cli("-m", "harbor.cli.main", "run", "--path", output / entry["path"],
                 "--agent", "oracle", "--n-concurrent", 1, "--jobs-dir", tmp_path / "jobs", "--job-name", "export")
    assert result.returncode == 0, result.stdout + result.stderr
    result_path = next((tmp_path / "jobs/export").glob("*/result.json"))
    saved = json.loads(result_path.read_text())
    assert json.loads(result_path.with_name("lock.json").read_text())["task"]["digest"] == task_entry(task)["hash"]
    assert (Task(task).name, entry["name"], saved["task_name"], saved["verifier_result"]["rewards"]["reward"]) == (
        "buidlguidl/question", "buidlguidl/question", "buidlguidl/question", 1)
    assert saved["exception_info"] is None
