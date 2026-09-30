import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
import yaml

from ethevals.cli import main
from ethevals.files import content_hash, manifest
from ethevals.loader import load_eval
from support import fixture_config


def test_pack_edits_change_only_opted_in_hashes_and_preserve_captured_bytes(folder, tmp_path, monkeypatch):
    pack = tmp_path / "skills"
    skill = pack / "units"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: units\ndescription: Ethereum units.\n---\nRead references/units.txt.\n")
    reference = skill / "references/units.txt"
    reference.write_text("One ether is 10^18 wei.")
    monkeypatch.setattr("ethevals.skills.PACK", pack)
    config = fixture_config()
    without = load_eval(folder, config)
    assert without.hash == content_hash(manifest(folder))
    path = folder / "eval.yaml"
    declaration = yaml.safe_load(path.read_text())
    declaration["modes"].append("skills")
    path.write_text(yaml.safe_dump(declaration))
    before = load_eval(folder, config)
    (pack / "README.md").write_text("Pack provenance.")
    (pack / "notes.txt").write_text("Top-level notes.")
    unchanged = load_eval(folder, config)
    assert unchanged.hash == before.hash
    assert sorted(name for name in unchanged.files if name.startswith("/skills/")) == [
        "/skills/units/SKILL.md", "/skills/units/references/units.txt"]
    reference.write_text("One gwei is 10^9 wei.")
    after = load_eval(folder, config)
    assert after.skills[0].references == {"units.txt": b"One gwei is 10^9 wei."}
    assert before.skills[0].references == {"units.txt": b"One ether is 10^18 wei."}
    assert before.hash != after.hash
    assert after.files["/skills/units/references/units.txt"] == b"One gwei is 10^9 wei."
    declaration["modes"].remove("skills")
    path.write_text(yaml.safe_dump(declaration, default_flow_style=None))
    assert load_eval(folder, config).hash == without.hash


def test_validate_rejects_a_skill_name_that_differs_from_its_folder(folder, tmp_path, monkeypatch, capsys):
    skill = tmp_path / "skills/units"
    skill.mkdir(parents=True)
    path = skill / "SKILL.md"
    path.write_text("---\nname: wrong\ndescription: Ethereum units.\n---\nRead this.\n")
    monkeypatch.setattr("ethevals.skills.PACK", skill.parent)
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["modes"] = ["skills"]
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    with pytest.raises(SystemExit) as error:
        main(["validate", "--evals", str(folder)])
    assert error.value.code == 2
    assert "Skill name 'wrong' does not match directory name 'units'" in capsys.readouterr().err
    path.write_text(path.read_text().replace("name: wrong", "name: units"))
    assert main(["validate", "--evals", str(folder)]) == 0
    assert "concepts/quiz " in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["reference", "empty"])
@pytest.mark.parametrize("modes,expected", [
    (["skills"], "skills"), (["internet", "skills"], "internet"), (["skills", "vanilla"], "vanilla"),
])
def test_free_checks_include_agent_only_quizzes(folder, tmp_path, answer, modes, expected):
    import shutil
    from ethevals.actors import select_actors
    from ethevals.planning import plan
    config = fixture_config()
    vanilla = tmp_path / "concepts/vanilla"
    shutil.copytree(folder, vanilla)
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["modes"] = modes
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    evaluations = [load_eval(folder, config)]
    evaluations.append(load_eval(vanilla, config))
    agents_for, _ = select_actors(config, answer=answer)
    report = plan(evaluations, config, agents_for, [], epochs=1).report
    assert sorted((row["eval_id"], row["mode"]) for row in report["missing"]) == [
        ("concepts/quiz", expected), ("concepts/vanilla", "vanilla")]


def test_skill_index_preserves_workspace_instructions(folder, monkeypatch):
    from ethevals.agents import HARNESSES, internet_solver
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["modes"].append("skills")
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    instructions = folder / "workspace/CLAUDE.md"
    instructions.write_text("Keep the author's instructions.")
    config = fixture_config()
    evaluation = load_eval(folder, config)
    class Workspace:
        async def read_file(self, path):
            return instructions.read_text()
        async def write_file(self, path, text):
            instructions.write_text(text)
    def factory(model, **settings):
        async def solve(state, generate):
            return [skill.name for skill in settings["skills"] or []]
        return solve
    monkeypatch.setattr("ethevals.agents.sandbox", Workspace)
    monkeypatch.setitem(HARNESSES, "claude_code", replace(HARNESSES["claude_code"], factory=factory))
    solve = internet_solver(config, config.agents["claude-code-opus-5.5"], evaluation.skills)
    assert asyncio.run(solve(SimpleNamespace(choices=[]), None)) == ["standards"]
    assert instructions.read_text().startswith("Keep the author's instructions.\n\n# Ethereum skills\n")
