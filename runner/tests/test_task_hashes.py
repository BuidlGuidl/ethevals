import json
from pathlib import Path
import subprocess

import pytest

from ethevals.job_config import load_job
from ethevals.jobs import plan, task_entry
from ethevals.stamp_rows import stamp_file, stamp_rows
from test_jobs import job_config, task_folder


@pytest.mark.parametrize("filename", ["README.md", "solution/solve.sh", "task.toml"])
def test_changes_outside_the_agent_and_checks_keep_finished_trials(tmp_path, filename):
    config, task = load_job(job_config(tmp_path, "free")), task_folder(tmp_path)
    row, = plan([task], config, [], n_attempts=1)["missing"]
    row.update(status="passed")
    file = task / filename
    file.write_text(file.read_text().replace("Check a reply.", "Check a unit.") if filename == "task.toml" else "Changed.\n")
    report = plan([task], config, [row], n_attempts=1)
    assert (report["missing_trials"], len(report["selected"]), report["worst_case_usd"]) == (0, 1, 0)
    assert task_entry(task)["hash"] != row["task_hash"]
    assert task_entry(task)["checks_hash"] == row["checks_hash"]


@pytest.mark.parametrize("filename", ["instruction.md", "environment/Dockerfile", "unknown-input.txt"])
def test_agent_changes_rerun_every_mode(tmp_path, filename):
    config, task = load_job(job_config(tmp_path, "free")), task_folder(tmp_path)
    config.modes = ["vanilla", "internet", "skills"]
    config.agents["local"].modes = ["internet", "skills"]
    config.agents["bare"] = config.agents["local"].model_copy(update={"modes": ["vanilla"]})
    declaration = task / "task.toml"
    declaration.write_text(declaration.read_text().replace('["internet"]', '["vanilla", "internet", "skills"]'))
    previous = [{**row, "status": "passed"} for row in plan([task], config, [], n_attempts=1)["missing"]]
    file = task / filename
    file.write_text((file.read_text() if file.exists() else "") + "Changed.\n")
    assert [(row["mode"], row["trial"], row["retry"]) for row in plan([task], config, previous, n_attempts=1)["missing"]] == [
        ("internet", 1, 0), ("skills", 1, 0), ("vanilla", 1, 0)]


def test_switch_over_uses_the_historical_folder_and_can_repeat_after_check_edits(tmp_path):
    task = task_folder(tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "tasks"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.org",
                    "commit", "-qm", "Save the task"], check=True)
    entry = task_entry(task)
    row = {"schema_version": 8, "task_id": entry["id"], "task_hash": entry["hash"], "status": "failed", "judge": None}
    (task / "tests/test.sh").write_text("Changed checks.\n")
    stamped, = stamp_rows([row], tmp_path)
    assert {key: stamped[key] for key in ("instruction_hash", "environment_hash", "checks_hash")} == {
        key: entry[key] for key in ("instruction_hash", "environment_hash", "checks_hash")}
    assert (stamped["schema_version"], stamped["status"], stamped["task_hash"]) == (8, "failed", row["task_hash"])
    assert stamp_rows([stamped, row], tmp_path) == [stamped, stamped]
    path = tmp_path / "rows.jsonl"
    original = json.dumps({**row, "task_hash": "sha256:missing"}) + "\n"
    path.write_text(original)
    with pytest.raises(ValueError, match="no rows changed"):
        stamp_file(path, tmp_path)
    assert path.read_text() == original
