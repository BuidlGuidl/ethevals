from ethevals.rows import read_rows

from support import eval_cli, fixture_quiz


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
