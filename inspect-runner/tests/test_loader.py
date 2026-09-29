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


@pytest.mark.parametrize("file,addition,key", [
    ("eval.yaml", "unexpected: true\n", "unexpected"),
    ("scorer/target.yaml", "unexpected: true\n", "unexpected"),
    ("eval.yaml", "addresses: {registry: 0x1234}\n", "addresses"),
])
def test_loader_rejects_unknown_keys(folder, file, addition, key):
    path = folder / file
    path.write_text(path.read_text() + addition)
    with pytest.raises(ValueError) as error:
        load_eval(folder, fixture_config())
    assert str(path) in str(error.value)
    assert key in str(error.value)


@pytest.mark.parametrize("target", ["8004", "1.10", "0x1234", '["8004", 42]'])
def test_loader_rejects_numeric_targets(folder, target):
    path = folder / "scorer/target.yaml"
    path.write_text(f"target: {target}\n")
    with pytest.raises(ValueError) as error:
        load_eval(folder, fixture_config())
    assert f"{path}: target" in str(error.value)


def test_loader_requires_scorer_file(folder):
    path = folder / "scorer/target.yaml"
    path.unlink()
    with pytest.raises(ValueError) as error:
        load_eval(folder, fixture_config())
    assert str(path.parent) in str(error.value)


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
    for name in ("lib", "out", "cache"):
        path = folder / "workspace/src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    sample = load_eval(folder, fixture_config()).sample()
    assert {name: sample.files["/workspace/src/" + name] for name in ("lib", "out", "cache")} == {
        "lib": inline_file(b"lib"), "out": inline_file(b"out"), "cache": inline_file(b"cache")}
    (folder / "workspace/src/scorer").mkdir()
    (folder / "workspace/src/scorer/lib").write_text("nested")
    assert load_eval(folder, fixture_config()).sample().files["/workspace/src/scorer/lib"] == inline_file(b"nested")


@pytest.mark.parametrize("name", ["scorer/tests/cache", "workspace/cache", "workspace/lib/cache"])
def test_reserved_symlinks_are_rejected_before_read(tmp_path, name):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(tmp_path / "host-secret")
    with pytest.raises(ValueError, match="symlinks"):
        load_eval(folder, fixture_config())


def test_reserved_scorer_directory_is_rejected(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    path = folder / "scorer/tests/lib/Extra.t.sol"
    path.parent.mkdir()
    path.write_text("contract Extra { function testFree() public {} }")
    with pytest.raises(ValueError, match="reserved names"):
        load_eval(folder, fixture_config())


def test_eval_root_cannot_be_a_symlink(tmp_path):
    folder = tmp_path / "building/alias"
    folder.parent.mkdir()
    folder.symlink_to(BUILD, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        load_eval(folder, fixture_config())


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


def test_quiz_internet_has_no_foundry_files_or_note():
    config = fixture_config()
    evaluation = load_eval(ROOT / "inspect-runner/tests/fixtures/concepts/wei-per-ether", config)
    task = build_task(evaluation, config, None, "internet", "reference", 1)
    assert task.dataset[0].input.startswith("How many wei equal one ether?\nYour container has a ")
    assert "Foundry" not in task.dataset[0].input
    assert task.dataset[0].files == {"/workspace/.gitkeep": "data:application/octet-stream;base64,"}
    assert task.dataset[0].sandbox.type == "ethevals_docker"


def test_author_foundry_file_is_rejected(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    (folder / "workspace/foundry.toml").write_text("[profile.default]\nffi=true\n")
    with pytest.raises(ValueError, match="runner-owned"):
        load_eval(folder, fixture_config())


def test_hard_link_is_rejected(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    outside = tmp_path / "outside.txt"
    outside.write_text("inert sentinel")
    os.link(outside, folder / "workspace/probe.txt")
    with pytest.raises(ValueError, match="hard links"):
        load_eval(folder, fixture_config())


def test_finder_junk_under_scorer_does_not_change_hash(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    config = fixture_config()
    before = load_eval(folder, config)
    (folder / "scorer/.DS_Store").write_bytes(b"Finder metadata")
    after = load_eval(folder, config)
    assert after.id == "building/token"
    assert after.hash == before.hash


def test_compose_directory_reports_a_load_error(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    (folder / "compose.yaml").mkdir()
    with pytest.raises(ValueError, match="must be a regular file"):
        load_eval(folder, fixture_config())


def test_scenario_is_parked(tmp_path):
    folder = tmp_path / "concepts/review"
    (folder / "workspace").mkdir(parents=True)
    (folder / "scorer").mkdir()
    (folder / "scorer/scorer.yaml").write_text("scorers: []\n")
    path = folder / "eval.yaml"
    path.write_text("type: scenario\nprompt: Review this.\nmotivation: Check review.\nmodes: [internet]\n")
    with pytest.raises(ValueError) as error:
        load_eval(folder, fixture_config())
    assert str(error.value) == f"{path.resolve()}: type: scenario is not supported yet"


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
