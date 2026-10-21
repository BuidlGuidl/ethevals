import json
from pathlib import Path
import shutil

from harbor.models.registry import Registry
import pytest
import yaml

from ethevals.cli import main
from ethevals.hf import write_hf


ROOT = Path(__file__).resolve().parents[2]


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
        ("ethevals", "1.0", [("concepts--question", "tasks/concepts--question", None)])]
    assert yaml.safe_load((output / "eval.yaml").read_text())["evaluation_framework"] == "harbor"
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
