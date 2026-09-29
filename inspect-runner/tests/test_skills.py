import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ethevals.cli import main
from ethevals.files import content_hash, manifest
from ethevals.loader import load_eval
from support import build_task, eval_cli, fixture_config


def test_skills_plan_keeps_the_harness(folder, tmp_path):
    path = folder / "eval.yaml"
    declaration = yaml.safe_load(path.read_text())
    declaration["modes"] = ["vanilla", "internet", "skills"]
    path.write_text(yaml.safe_dump(declaration))
    result = eval_cli("plan", "--evals", folder, "--agents", "claude-code-opus-5.5", "--modes", "skills",
                      "--epochs", "1", "--budget", "12", "--output", tmp_path / "plan")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    row = report["missing"][0]
    assert (report["missing_epochs"], report["worst_case_usd"], report["within_budget"]) == (1, 10, True)
    assert (row["mode"], row["harness"], row["per_attempt_usd"]) == (
        "skills", "claude_code", 5)


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


@pytest.mark.parametrize("agent,name", [("claude-code-opus-5.5", "CLAUDE.md"), ("codex-cli-gpt-5.5", "AGENTS.md"), ("opencode-kimi-k3", "AGENTS.md")])
@pytest.mark.parametrize("existing", [None, "Keep the author's instructions."])
def test_skill_index_preserves_workspace_instructions_and_internet_prompt(folder, monkeypatch, agent, name, existing):
    from ethevals.agents import HARNESSES, internet_solver
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["modes"].append("skills")
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    if existing is not None:
        (folder / "workspace" / name).write_text(existing)
    config = fixture_config()
    evaluation = load_eval(folder, config)
    internet = build_task(evaluation, config, agent, "internet", None, 1)
    skills = build_task(evaluation, config, agent, "skills", None, 1)
    class Workspace:
        async def read_file(self, path):
            return (folder / path.removeprefix("/")).read_text()

        async def write_file(self, path, text):
            (folder / path.removeprefix("/")).write_text(text)

    def factory(model, **settings):
        async def solve(state, generate):
            path = folder / "workspace" / name
            return path.read_text() if path.exists() else "", [skill.name for skill in settings["skills"] or []]
        return solve

    harness = config.agents[agent].harness
    monkeypatch.setattr("ethevals.agents.sandbox", Workspace)
    monkeypatch.setitem(HARNESSES, harness, replace(HARNESSES[harness], factory=factory))
    state = SimpleNamespace(choices=[])
    ordinary = internet_solver(config, config.agents[agent])
    assert asyncio.run(ordinary(state, None)) == (existing or "", [])
    solve = internet_solver(config, config.agents[agent], evaluation.skills)
    instructions, installed = asyncio.run(solve(state, None))
    prefix = existing + "\n\n" if existing else ""
    assert instructions.startswith(prefix + "# Ethereum skills\n")
    assert "- standards: Ethereum token and protocol standards" in instructions
    assert installed == ["standards"]
    assert skills.dataset[0].input == internet.dataset[0].input
    assert skills.metadata["search_limit"] == internet.metadata["search_limit"] == 20
    assert skills.working_limit == 300
    assert skills.time_limit >= 3 * skills.working_limit
    assert skills.time_limit / 2 >= skills.metadata["scoring_limit_seconds"]


def test_missing_skill_file_reports_the_real_pack_folder(folder, tmp_path, monkeypatch):
    pack = tmp_path / "skills"
    (pack / "units").mkdir(parents=True)
    (pack / "units/notes.md").write_text("Missing the skill file.")
    monkeypatch.setattr("ethevals.skills.PACK", pack)
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["modes"] = ["skills"]
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    with pytest.raises(ValueError) as error:
        load_eval(folder, fixture_config())
    assert str(error.value) == f"{pack}: SKILL.md not found in: {pack / 'units'}"


@pytest.mark.parametrize("answer", ["reference", "empty"])
@pytest.mark.parametrize("alongside_vanilla", [False, True])
@pytest.mark.parametrize("modes,expected", [
    (["skills"], "skills"), (["internet", "skills"], "internet"), (["skills", "vanilla"], "vanilla"),
])
def test_free_checks_include_agent_only_quizzes(folder, tmp_path, answer, alongside_vanilla, modes, expected):
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
    if alongside_vanilla:
        evaluations.append(load_eval(vanilla, config))
    agents_for, _ = select_actors(config, answer=answer)
    report = plan(evaluations, config, agents_for, [], epochs=1).report
    assert sorted((row["eval_id"], row["mode"]) for row in report["missing"]) == [
        ("concepts/quiz", expected), *([("concepts/vanilla", "vanilla")] if alongside_vanilla else [])]


def test_skills_only_act_gets_a_free_reference_check(tmp_path):
    import shutil
    from ethevals.actors import select_actors
    folder = tmp_path / "transactions/transfer"
    root = Path(__file__).resolve().parents[2]
    shutil.copytree(root / "evals/transactions/send-six-decimal-token", folder)
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["modes"] = ["skills"]
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    config = fixture_config()
    evaluation = load_eval(folder, config)
    agents_for, _ = select_actors(config, answer="reference")
    assert [(mode, actor.free_check, actor.sandbox_for(evaluation)) for mode, actor in agents_for(evaluation)] == [
        ("skills", True, True)]
    assert evaluation.scorer_kinds == ["check_script", "rubric"]
