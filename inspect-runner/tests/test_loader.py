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
BUILD = ROOT / "evals/building/erc20-points-token"


def test_loader_preserves_target_and_prompt(folder):
    (folder / "eval.yaml").write_text("motivation: Test a literal answer.\nprompt: Say hello.\nmodes: [internet]\n")
    (folder / "scorer/target.yaml").write_text('target: ["hello", "hi"]\n')
    (folder / "workspace/hello.txt").write_text("public workspace")
    (folder / "scorer/secret.txt").write_text("private scorer")
    sample = load_eval(folder, fixture_config()).sample()
    assert (sample.id, sample.input, sample.target) == ("concepts/quiz", "Say hello.", ["hello", "hi"])
    assert sample.files == {"/workspace/hello.txt": inline_file(b"public workspace")}


def test_hash_tracks_every_file_and_name(folder):
    (folder / "eval.yaml").write_text("motivation: Check files.\nprompt: Say hello.\nmodes: [internet]\n")
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
    (folder / "eval.yaml").write_text("motivation: Check files.\nprompt: Say hello.\nmodes: [internet]\n")
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
        "motivation: Check units.\nprompt: How many wei?\n"
        "modes: [vanilla, internet]\nchoices: null\n"
    )
    (folder / "scorer" / "target.yaml").write_text('target: "1000000000000000000"\n')
    output = tmp_path / "export"
    result = subprocess.run(
        [sys.executable, "-m", "ethevals.cli", "catalog", "--evals", str(folder), "--output", str(output), "--config", str(config_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "catalog.json").read_text()) == [{
        "id": "concepts/units",
        "hash": "cc49e54adbee0419687e4cac9914259b3d0c0798bd774cc2d1d51f82965b0090",
        "pillar": "concepts", "chain": None, "motivation": "Check units.",
        "prompt": "How many wei?", "modes": ["vanilla", "internet"], "choices": None,
    }]


@pytest.mark.parametrize("file,content", [
    ("eval.yaml", "prompt: Hello\nmotivation: Test\nmodes: [vanilla]\nextra: true\n"),
    ("eval.yaml", "prompt: Hello\nmotivation: Test\nmodes: [vanilla]\nchoices: [wei, ' ', ether]\n"),
    ("scorer/target.yaml", "target: wei\nextra: true\n"),
    ("scorer/target.yaml", "target: 8004\n"),
    ("scorer/target.yaml", None),
])
def test_loader_rejects_broken_declarations(folder, file, content):
    (folder / "scorer/target.yaml").write_text("target: A\n")
    path = folder / file
    path.write_text(content) if content is not None else path.unlink()
    with pytest.raises(ValueError):
        load_eval(folder, fixture_config())


@pytest.mark.parametrize("name,kind", [
    ("workspace/notes.txt", "symlink"), ("workspace/probe.txt", "hardlink"),
    ("scorer/tests/lib/Extra.t.sol", "file"),
])
def test_loader_rejects_unsafe_author_files(tmp_path, name, kind):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        (tmp_path / "host-secret").write_text("private host data")
        path.symlink_to(tmp_path / "host-secret")
    elif kind == "hardlink":
        outside = tmp_path / "outside.txt"
        outside.write_text("host file")
        os.link(outside, path)
    else:
        path.write_text("runner-owned path")
    with pytest.raises(ValueError):
        load_eval(folder, fixture_config())


def test_eval_root_cannot_be_a_symlink(tmp_path):
    folder = tmp_path / "linked"
    folder.symlink_to(BUILD)
    with pytest.raises(ValueError, match="symlinks"):
        load_eval(folder, fixture_config())


@pytest.mark.parametrize("value", ["hardhat", "{fork: mainnet, block: 23819000}"])
def test_chain_rejects_other_values(folder, value):
    path = folder / "eval.yaml"
    path.write_text(path.read_text() + f"chain: {value}\n")
    with pytest.raises(ValueError, match="chain"):
        load_eval(folder, fixture_config())


@pytest.mark.parametrize("word", ["EPOCHS", "Grader", "rubrics", "score", "benchmarks", "evals", "being   tested"])
@pytest.mark.parametrize("destination", ["prompt", "workspace", "choices"])
def test_agent_word_lint_rejects_whole_words(folder, word, destination):
    (folder / "eval.yaml").write_text(f"motivation: Check words.\nprompt: {word if destination == 'prompt' else 'Say hello.'}\nmodes: [internet]\n")
    if destination == "workspace":
        (folder / "workspace/note.txt").write_text(f"Please read the {word}.")
    elif destination == "choices":
        with (folder / "eval.yaml").open("a") as declaration:
            declaration.write(f"choices: ['hello', '{word}']\n")
    with pytest.raises(ValueError, match="agent-visible text contains forbidden word"):
        load_eval(folder, fixture_config())


def test_agent_word_lint_allows_substrings_and_binary_files(folder):
    (folder / "eval.yaml").write_text("motivation: Check words.\nprompt: Evaluate the scoreboard.\nmodes: [internet]\n")
    (folder / "workspace/image.bin").write_bytes(b"\xffscore")
    assert load_eval(folder, fixture_config()).sample().input == "Evaluate the scoreboard."


@pytest.mark.parametrize("change,reason", [
    ("workspace", "vanilla requires"), ("tests", "vanilla requires"),
    ("chain", "vanilla requires"), ("solution", "solution is required"),
])
def test_folder_rules(folder, change, reason):
    if change == "workspace":
        (folder / "workspace/.gitkeep").write_bytes(b"")
    elif change == "chain":
        path = folder / "eval.yaml"
        path.write_text(path.read_text() + "chain: anvil\n")
    else:
        (folder / "scorer/tests").mkdir()
        (folder / "scorer/tests/Check.t.sol").write_text("contract Check { function test_ok() public {} }")
        if change == "solution":
            (folder / "eval.yaml").write_text("motivation: Check files.\nprompt: Say hello.\nmodes: [internet]\n")
    with pytest.raises(ValueError, match=reason):
        load_eval(folder, fixture_config())


@pytest.mark.parametrize("source,rubric,target,reason", [
    ("function test_shared() public {}", "## test_shared\nIs it correct?", "answer", "duplicate check name"),
    ("function test_shared() public {}", "## other\nIs it correct?", "test_shared", "duplicate check name"),
    ("function test_ok() public {}", "## answer\nIs it correct?", "answer", "duplicate check name"),
    ("function test_ok() public {}", "## compile\nIs it correct?", "answer", "reserved"),
    ("function test_ok() public {}", "## other\nIs it correct?", "compile", "reserved"),
    ("function testFailBad() public {}", "## other\nIs it correct?", "answer", "testFail"),
    ("function test_same() public {} function test_same(uint n) public {}", "## other\nIs it correct?", "answer", "duplicate check name"),
])
def test_check_names_are_unique_across_scorers(tmp_path, source, rubric, target, reason):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    (folder / "scorer/tests/BuilderPoints.t.sol").write_text(f"contract Check {{ {source} }}")
    (folder / "scorer/rubric.md").write_text(rubric)
    (folder / "scorer/target.yaml").write_text(f"name: {target}\ntarget: done\n")
    with pytest.raises(ValueError, match=reason):
        load_eval(folder, fixture_config())


def test_mixed_scorers_preserve_author_workspace(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    (folder / "scorer/target.yaml").write_text("target: done\n")
    evaluation = load_eval(folder, fixture_config())
    assert evaluation.sample().files["/workspace/foundry.toml"] == inline_file(
        b'[profile.default]\nsrc = "src"\ntest = "test"\nlibs = ["lib"]\nsolc = "0.8.30"\n')
    assert evaluation.sample().input == evaluation.declaration.prompt


def test_validate_rejects_tests_with_only_a_helper(tmp_path):
    from support import eval_cli
    folder = tmp_path / "building" / "helpers"
    shutil.copytree(BUILD, folder)
    (folder / "scorer/tests/BuilderPoints.t.sol").unlink()
    (folder / "scorer/tests/Helper.sol").write_text("contract Helper {}")
    result = eval_cli("validate", "--evals", folder)
    assert result.returncode == 2
    assert "no runner claims a file in scorer/tests/" in result.stderr


def test_unclaimed_helper_functions_are_not_checks(tmp_path):
    folder = tmp_path / "building" / "helpers"
    shutil.copytree(BUILD, folder)
    (folder / "scorer/tests/Helper.sol").write_text("contract Helper { function test_name_and_symbol() public {} }")
    evaluation = load_eval(folder, fixture_config())
    assert evaluation.scorer_kinds == ["tests", "rubric"]
