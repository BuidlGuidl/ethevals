import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ethevals.job_config import JudgeSettings, load_job
from ethevals.jobs import decide_saved_row, plan, task_entry
from ethevals.regrade import regrade_options
from ethevals.trial_rows import fold_rows, recover_regrades, results_row, trial_identity, write_rows
from support import recorded_trial
from test_agent_judges import agent_task
from test_jobs import job_config

ROOT = Path(__file__).resolve().parents[2]
OLD_HASHES = {
    "act/treasury-eth-sale": "sha256:bad31e5877358f6fba5cd452f41431aab13f0408b095359a4f94ad225d690c57",
    "build/voting-page": "sha256:b26de136ea3bf4cd0bee24947ad664edecfeebe601d815c195dbbb76b10fca6e",
}
KEPT = ("fair_price", "report_matches_chain", "nothing_left_behind", "once_per_quarter")


def evidence_trial(tmp_path, monkeypatch, name):
    from ethevals.harbor_tasks import task_host_variables

    task = ROOT / "tasks" / name
    for variable in task_host_variables(task):
        monkeypatch.setenv(variable, "offline-rpc")
    config = load_job(job_config(tmp_path, "free"))
    config.judge = JudgeSettings()
    item, = plan([task], config, [], n_attempts=1)["missing"]
    folder = tmp_path / "saved"
    recorded_trial(folder, task)
    row = results_row(folder, item)
    row.update(status="passed", checks_hash=OLD_HASHES[name], checks_inputs={"tests/test.sh": "old",
               "@artifacts": item["checks_inputs"].get("@artifacts")})
    return task, config, row


@pytest.mark.parametrize("name", list(OLD_HASHES))
def test_regrade_from_plans_passes_and_fails_before_the_tasks_own_kind(tmp_path, monkeypatch, name):
    task, config, row = evidence_trial(tmp_path, monkeypatch, name)
    other = {**row, "trial": 3, "checks_hash": "sha256:" + "0" * 64,
             "verifier_files": None, "verifier_url": None}
    report = plan([task], config, [row, {**row, "trial": 2, "status": "failed"}, other],
                  n_attempts=3, saved_work=tmp_path / "cache")
    assert [(item["trial"], item["kind"], item["judge_required"]) for item in report["regrades"]] == [
        (1, "evidence", True), (2, "evidence", True)]
    reason = ("Saved work is gone: No saved work is published" if name.startswith("build/") else
              "The changed checks cannot use a saved-input regrade.")
    assert [(item["trial"], item["rerun_reason"]) for item in report["missing"]] == [(3, reason)]


@pytest.mark.parametrize("name", list(OLD_HASHES))
def test_regrade_from_reruns_when_check_output_is_gone(tmp_path, monkeypatch, name):
    task, config, row = evidence_trial(tmp_path, monkeypatch, name)
    row.update(verifier_files=None, verifier_url=None)
    report = plan([task], config, [row], n_attempts=1, saved_work=tmp_path / "cache")
    assert (report["regrade_trials"], [(item["trial"], item["rerun_reason"]) for item in report["missing"]]) == (
        0, [(1, "Saved work is gone: The saved judge input is unavailable")])


@pytest.mark.parametrize("missing", [False, True])
def test_sale_script_regrade_preserves_only_its_current_records(tmp_path, missing):
    records = {name: {"passed": index % 2 == 0, "reason": f"Saved result {index}."}
               for index, name in enumerate((*KEPT, "swap_has_minimum", "swap_has_deadline"))}
    if missing:
        del records["once_per_quarter"]
    output = tmp_path / "checks.json"
    output.write_text(json.dumps(records))
    for filename in ("script-source.txt", "chain-evidence.json", "rerun-evidence.json"):
        (tmp_path / filename).write_bytes(b"Saved evidence.\n")
    result = subprocess.run([sys.executable, ROOT / "tasks/act/treasury-eth-sale/tests/sale_checks.py",
                             "--output", tmp_path], env={**os.environ, "ETHEVALS_REGRADE_ITEM": "saved-item.json"},
                            capture_output=True, text=True)
    if missing:
        assert result.returncode != 0 and "once_per_quarter" in result.stderr
        assert json.loads(output.read_text()) == records
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(output.read_text()) == {name: records[name] for name in KEPT}
    assert [(tmp_path / name).read_bytes() for name in
            ("script-source.txt", "chain-evidence.json", "rerun-evidence.json")] == [b"Saved evidence.\n"] * 3


@pytest.mark.parametrize("workspace", [False, True])
def test_browser_judge_only_changes_use_the_workspace_kind_when_available(tmp_path, workspace):
    task, config = agent_task(tmp_path, live=True)
    if workspace:
        page = tmp_path / "tasks/build/question"
        page.parent.mkdir()
        task.rename(page)
        task = page
        settings = task / "task.toml"
        settings.write_text('artifacts = [{source = "/workspace"}]\n' + settings.read_text().replace(
            'pillar = "concepts"', 'pillar = "build"'))
    before = task_entry(task, config)
    judge = task / "tests/judge.toml"
    judge.write_text(judge.read_text().replace("unit explained?", "unit explained correctly?"))
    current = {**task_entry(task, config), "regrade": regrade_options(task)}
    assert decide_saved_row({**before, "status": "passed"}, current, config.retry) == (
        {"action": "regrade", "kind": "workspace", "judge_required": True} if workspace else
        {"action": "rerun", "reason": "The judge needs a live browser or chain."})


def test_finished_saved_output_regrade_folds_eight_checks_and_keeps_original_trial_fields(tmp_path, monkeypatch):
    task, config, old = evidence_trial(tmp_path, monkeypatch, "act/treasury-eth-sale")
    old.update(model_cost_usd=1.25, judge_cost_usd=0.5, trajectory_url="https://example.org/original.json")
    report = plan([task], config, [old], n_attempts=1, saved_work=tmp_path / "cache")
    item, = report["regrades"]
    assert item["kind"] == "evidence"
    output = tmp_path / "output"
    job = output / "jobs/checked"
    verifier = job / "0/verifier"
    verifier.mkdir(parents=True)
    (job / "0/agent").mkdir()
    (job / "0/agent/trajectory.json").write_bytes(Path(old["trajectory_file"]).read_bytes())
    (job / "regrade.json").write_text(json.dumps([item]))
    (job / "0/regrade-finished.json").write_text(json.dumps("2026-11-11T12:00:00Z"))
    code = {name: {"passed": index != 1, "reason": f"Saved result {index}."} for index, name in enumerate(KEPT)}
    judged = {name: {"passed": True, "reason": "New judge answer."} for name in (
        "checks_receipt_status", "refusal_checks_price", "swap_has_minimum", "swap_has_deadline")}
    (verifier / "checks.json").write_text(json.dumps(code))
    (verifier / "reward.json").write_text('{"reward": 0.0}')
    (verifier / "reward-details.json").write_text(json.dumps({
        "code": {"kind": "programmatic", "criteria": [
            {"name": name, "value": int(record["passed"]), "reasoning": record["reason"]} for name, record in code.items()]},
        "script": {"kind": "agent", "judge": {"agent": "claude-code", "model": config.judge.model,
            "reasoning_effort": "high"}, "usage": {"cost_usd": 0.75}, "criteria": [
            {"name": name, "value": 1, "raw": "yes", "reasoning": record["reason"]} for name, record in judged.items()]}}))
    rows = fold_rows([old], recover_regrades(output))
    write_rows(output / "rows.jsonl", rows)
    row, = [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()]
    assert row["checks"] == {**code, **judged}
    assert (row["status"], row["checks_hash"], row["checks_generation"], row["regraded_at"], row["judge_cost_usd"]) == (
        "failed", item["checks_hash"], 1, "2026-11-11T12:00:00Z", 0.75)
    assert trial_identity(row) == trial_identity(old)
    original_fields = ("agent", "agent_version", "model", "effort", "paid_by", "model_cost_usd",
                       "total_tokens", "completed_at", "total_seconds", "working_seconds", "trajectory_url")
    assert {key: row[key] for key in original_fields} == {key: old[key] for key in original_fields}
    assert row["trajectory_download_url"] == "https://example.org/original.json"
    assert (row["judge"], row["judge_paid_by"], row["verifier_files"], row["verifier_url"]) == (
        config.judge.identity(), "plan", str(verifier.resolve()), None)
    assert Path(row["trajectory_file"]).read_bytes() == Path(old["trajectory_file"]).read_bytes()
