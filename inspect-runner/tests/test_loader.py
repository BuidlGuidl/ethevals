from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

from ethevals.files import inline_file
from ethevals.loader import load_eval
import pytest

from support import build_task, fixture_config


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "inspect-runner/tests/fixtures/building/erc20-points-token"


def test_loader_preserves_target_and_prompt(folder):
    (folder / "workspace/.gitkeep").unlink()
    (folder / "eval.yaml").write_text("type: quiz\nmotivation: Test a literal answer.\nprompt: Say hello.\nmodes: [internet]\n")
    (folder / "scorer/target.yaml").write_text('target: ["hello", "hi"]\n')
    (folder / "workspace/hello.txt").write_text("public workspace")
    (folder / "scorer/secret.txt").write_text("private scorer")
    sample = load_eval(folder, fixture_config()).sample()
    assert (sample.id, sample.input, sample.target) == ("concepts/quiz", "Say hello.", ["hello", "hi"])
    assert sample.files == {"/workspace/hello.txt": inline_file(b"public workspace")}


def test_hash_tracks_every_file_and_name(folder):
    original = load_eval(folder, fixture_config()).hash
    path = folder / "workspace/code.txt"
    path.write_text("hello")
    added = load_eval(folder, fixture_config()).hash
    assert added != original
    path.write_text("goodbye")
    changed = load_eval(folder, fixture_config()).hash
    assert changed != added
    path.rename(folder / "workspace/renamed.txt")
    assert load_eval(folder, fixture_config()).hash != changed
    (folder / "workspace/renamed.txt").unlink()
    assert load_eval(folder, fixture_config()).hash == original


def test_hash_ignores_local_artifacts_but_includes_new_author_files(folder):
    (folder / "workspace/.gitkeep").unlink()
    original = load_eval(folder, fixture_config()).hash
    (folder / ".DS_Store").write_bytes(b"Finder")
    for name in ["out", "cache", "lib", "__pycache__"]:
        (folder / name).mkdir()
        (folder / name / "generated").write_text("local artifact")
        path = folder / "workspace" / name
        path.mkdir()
        (path / "generated").write_text("local artifact")
    assert load_eval(folder, fixture_config()).hash == original
    (folder / "workspace/code.sol").write_text("contract New {}")
    assert load_eval(folder, fixture_config()).hash != original
    assert load_eval(folder, fixture_config()).sample().files == {
        "/workspace/code.sol": inline_file(b"contract New {}")}


def test_loaded_eval_uses_captured_files(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    config = fixture_config()
    evaluation = load_eval(folder, config)
    (folder / "workspace/src/BuilderPoints.sol").write_text("modified after loading")
    (folder / "scorer/rubric.md").write_text("## replaced\nWrong question")
    task = build_task(evaluation, config, None, "internet", "reference", 1)
    from ethevals.files import inline_file
    assert task.dataset[0].files["/workspace/src/BuilderPoints.sol"] == inline_file((BUILD / "workspace/src/BuilderPoints.sol").read_bytes())
    assert evaluation.files["scorer/rubric.md"] == (BUILD / "scorer/rubric.md").read_bytes()
    assert load_eval(folder, config).hash != evaluation.hash


def test_catalog_exports_a_loaded_eval(tmp_path, config_path):
    folder = tmp_path / "concepts" / "units"
    (folder / "workspace").mkdir(parents=True)
    (folder / "scorer").mkdir()
    (folder / "eval.yaml").write_text(
        "type: quiz\nmotivation: Check units.\nprompt: How many wei?\n"
        "modes: [vanilla, internet]\nchoices: null\n"
    )
    (folder / "workspace" / "note.txt").write_text("public")
    (folder / "scorer" / "target.yaml").write_text('target: "1000000000000000000"\n')
    output = tmp_path / "export"
    result = subprocess.run(
        [sys.executable, "-m", "ethevals.cli", "catalog", "--evals", str(folder), "--output", str(output), "--config", str(config_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "catalog.json").read_text()) == [{
        "id": "concepts/units",
        "hash": "a1d1e1a5ef44c9e62560659297fd0c1771b030d190cc2b30ab14a5eeaab47d68",
        "pillar": "concepts", "type": "quiz", "motivation": "Check units.",
        "prompt": "How many wei?", "modes": ["vanilla", "internet"], "choices": None,
    }]


@pytest.mark.parametrize("file,content", [
    ("eval.yaml", "type: quiz\nprompt: Hello\nmotivation: Test\nmodes: [vanilla]\nextra: true\n"),
    ("eval.yaml", "type: scenario\nprompt: Hello\nmotivation: Test\nmodes: [internet]\n"),
    ("scorer/target.yaml", "target: wei\nextra: true\n"),
    ("scorer/target.yaml", "target: 8004\n"),
    ("scorer/target.yaml", None),
])
def test_loader_rejects_broken_declarations(folder, file, content):
    path = folder / file
    path.write_text(content) if content is not None else path.unlink()
    with pytest.raises(ValueError):
        load_eval(folder, fixture_config())


@pytest.mark.parametrize("name,kind", [
    ("scorer/tests/cache", "symlink"), ("workspace/probe.txt", "hardlink"),
    ("workspace/foundry.toml", "file"), ("scorer/tests/lib/Extra.t.sol", "file"),
])
def test_loader_rejects_unsafe_author_files(tmp_path, name, kind):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        path.symlink_to(tmp_path / "host-secret")
    elif kind == "hardlink":
        outside = tmp_path / "outside.txt"
        outside.write_text("host file")
        os.link(outside, path)
    else:
        path.write_text("runner-owned path")
    with pytest.raises(ValueError):
        load_eval(folder, fixture_config())
