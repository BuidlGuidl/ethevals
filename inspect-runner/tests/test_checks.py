import asyncio
from types import SimpleNamespace

from ethevals.checks import check_agent
from ethevals.loader import load_eval
from ethevals.rows import read_rows

from support import eval_cli, fixture_config, fixture_quiz


def test_reference_applies_target_and_solution(tmp_path, monkeypatch):
    evaluation = fixture_quiz(tmp_path, modes=["internet"], reference="wei")
    (evaluation.folder / "solution").mkdir()
    (evaluation.folder / "solution/note.txt").write_text("reference work")
    evaluation = load_eval(evaluation.folder, fixture_config())

    class Workspace:
        def __init__(self):
            self.files = {}

        async def write_file(self, path, data):
            self.files[path] = data

    async def solve(answer):
        box = Workspace()
        monkeypatch.setattr("ethevals.checks.sandbox", lambda: box)
        actor = check_agent(evaluation, answer, mode="internet")
        assert actor.sandbox_for(evaluation) is True

        async def generate(state):
            state.reply = (await actor.model.generate("Give the unit.")).completion
            return state

        state = await actor.solver_for(evaluation)(SimpleNamespace(), generate)
        return state.reply, box.files

    assert asyncio.run(solve("reference")) == ("wei", {"/workspace/note.txt": b"reference work"})
    assert asyncio.run(solve("empty")) == ("", {})
    assert check_agent(evaluation, "reference", mode="vanilla").sandbox_for(evaluation) is True


def test_check_skips_rubric_only_evals(tmp_path):
    target = fixture_quiz(tmp_path, "units")
    rubric = fixture_quiz(tmp_path, "discussion")
    (rubric.folder / "scorer/target.yaml").unlink()
    (rubric.folder / "scorer/rubric.md").write_text("## explained\nDid the reply explain the unit?\n")
    output = tmp_path / "results"
    result = eval_cli("check", "--evals", target.folder, rubric.folder, "--epochs", "1", "--output", output)
    assert result.returncode == 0, result.stderr
    assert [(row["eval_id"], row["status"]) for row in read_rows(output / "reference/rows.jsonl")] == [
        ("concepts/units", "passed")]
    assert [(row["eval_id"], row["status"]) for row in read_rows(output / "empty/rows.jsonl")] == [
        ("concepts/units", "failed")]
    assert eval_cli("check", "--evals", rubric.folder, "--output", tmp_path / "rubric").returncode == 0
