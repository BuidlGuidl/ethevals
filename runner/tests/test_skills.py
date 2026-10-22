from ethevals.skills import pack_skills
import pytest


def test_pack_captures_resources_and_ignores_root_notes(tmp_path, monkeypatch):
    skill = tmp_path / "skills/units"
    (skill / "references").mkdir(parents=True)
    instruction = b"---\nname: units\ndescription: Units.\n---\nRead references/unit.txt.\n"
    (skill / "SKILL.md").write_bytes(instruction)
    resource = skill / "references/unit.txt"
    resource.write_bytes(b"One metre.\n")
    monkeypatch.setattr("ethevals.skills.PACK", skill.parent)
    before = pack_skills()
    assert before.files == {
        "/skills/units/SKILL.md": instruction,
        "/skills/units/references/unit.txt": b"One metre.\n",
    }
    (skill.parent / "README.md").write_text("Pack notes.\n")
    assert pack_skills() == before
    resource.write_bytes(b"Two metres.\n")
    after = pack_skills()
    assert before.files["/skills/units/references/unit.txt"] == b"One metre.\n"
    assert after.files["/skills/units/references/unit.txt"] == b"Two metres.\n"
    assert before.hash != after.hash


def test_pack_requires_harbor_skill_folders(tmp_path, monkeypatch):
    skill = tmp_path / "skills/units"
    skill.mkdir(parents=True)
    (skill / "notes.md").write_text("A unit.\n")
    monkeypatch.setattr("ethevals.skills.PACK", skill.parent)
    with pytest.raises(ValueError, match="without SKILL.md"):
        pack_skills()
    (skill / "SKILL.md").write_text("A unit.\n")
    assert pack_skills().files == {
        "/skills/units/SKILL.md": b"A unit.\n", "/skills/units/notes.md": b"A unit.\n",
    }
