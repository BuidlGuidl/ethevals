import base64
import json
from pathlib import Path

import pytest
import yaml

from ethevals.cli import main
from ethevals.files import content_hash, manifest
from ethevals.loader import load_eval
from support import build_task, eval_cli, fixture_config


def test_skills_plan_reserves_search_and_keeps_the_harness(folder, tmp_path):
    path = folder / "eval.yaml"
    declaration = yaml.safe_load(path.read_text())
    declaration["modes"] = ["vanilla", "internet", "skills"]
    path.write_text(yaml.safe_dump(declaration))
    result = eval_cli("plan", "--evals", folder, "--agents", "opus", "--modes", "skills",
                      "--epochs", "1", "--budget", "12", "--output", tmp_path / "plan")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    row = report["missing"][0]
    assert (report["missing_epochs"], report["worst_case_usd"], report["within_budget"]) == (1, 12, True)
    assert (row["mode"], row["harness"], row["per_attempt_usd"], row["wall_seconds"]) == (
        "skills", "claude_code", 6, 1320)


def test_pack_edits_change_only_opted_in_hashes_and_preserve_captured_bytes(folder, tmp_path, monkeypatch):
    pack = tmp_path / "skills"
    skill = pack / "units"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: units\ndescription: Ethereum units.\n---\nRead references/units.txt.\n")
    reference = skill / "references/units.txt"
    reference.write_text("One ether is 10^18 wei.")
    monkeypatch.setattr("ethevals.loader.PACK", pack)
    config = fixture_config()
    without = load_eval(folder, config)
    assert without.hash == content_hash(manifest(folder))
    path = folder / "eval.yaml"
    declaration = yaml.safe_load(path.read_text())
    declaration["modes"].append("skills")
    path.write_text(yaml.safe_dump(declaration))
    before = load_eval(folder, config)
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
    monkeypatch.setattr("ethevals.loader.PACK", skill.parent)
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


@pytest.mark.parametrize("agent,name", [("opus", "CLAUDE.md"), ("codex", "AGENTS.md"), ("kimi", "AGENTS.md")])
def test_skill_index_preserves_workspace_instructions_and_internet_prompt(folder, agent, name):
    declaration = yaml.safe_load((folder / "eval.yaml").read_text())
    declaration["modes"].append("skills")
    (folder / "eval.yaml").write_text(yaml.safe_dump(declaration))
    (folder / "workspace" / name).write_text("Keep the author's instructions.")
    config = fixture_config()
    evaluation = load_eval(folder, config)
    internet = build_task(evaluation, config, agent, "internet", None, 1)
    skills = build_task(evaluation, config, agent, "skills", None, 1)
    instructions = base64.b64decode(skills.dataset[0].files[f"/workspace/{name}"].split(",", 1)[1]).decode()
    assert instructions.startswith("Keep the author's instructions.\n\n# Ethereum skills\n")
    assert "- standards: Ethereum token and protocol standards" in instructions
    assert base64.b64decode(internet.dataset[0].files[f"/workspace/{name}"].split(",", 1)[1]) == b"Keep the author's instructions."
    assert skills.dataset[0].input == internet.dataset[0].input
    assert skills.metadata["search_limit"] == internet.metadata["search_limit"] == 20
    assert (skills.working_limit, skills.time_limit) == (300, 900)


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
    assert evaluation.scorer_kinds == ["check_script"]
