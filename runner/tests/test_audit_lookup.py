import importlib.util
import json
from pathlib import Path

import pytest

from ethevals.job_config import JudgeSettings, load_job
from ethevals.jobs import plan, read_redo
from ethevals.trial_rows import fold_rows, recover_regrades, results_row, trial_identity
from support import recorded_trial
from test_jobs import job_config
from test_regrade import saved_trial

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks/build/audit-the-compact"
CLAIM = json.loads((TASK / "tests/regrade-from.json").read_text())


def helper():
    spec = importlib.util.spec_from_file_location("judge_trajectory", TASK / "tests/judge_trajectory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def old_audit_row(tmp_path):
    """A saved audit row from before the line and the lookup gate."""
    config = load_job(job_config(tmp_path, "free"))
    config.judge = JudgeSettings()
    item, = plan([TASK], config, [], n_attempts=1)["missing"]
    recorded_trial(tmp_path / "saved", TASK)
    row = results_row(tmp_path / "saved", item)
    row.update(status="passed", instruction_hash=CLAIM["instructions"][0], checks_hash=CLAIM["checks"][0],
               checks_inputs={"tests/test.sh": "old", "@artifacts": ["/workspace/findings.md"]})
    return config, item, row


def test_old_audit_rows_regrade_with_the_gate_and_errors_keep_their_retry(tmp_path):
    config, item, row = old_audit_row(tmp_path)
    error = {**row, "trial": 3, "status": "error", "error_kind": "execution", "retry": 0}
    report = plan([TASK], config, [row, {**row, "trial": 2, "status": "failed"}, error],
                  n_attempts=3, saved_work=tmp_path / "cache")
    assert [(entry["trial"], entry["kind"], entry["judge_required"], entry["instruction_hash"])
            for entry in report["regrades"]] == [(1, "evidence", True, item["instruction_hash"]),
                                                 (2, "evidence", True, item["instruction_hash"])]
    assert [(entry["trial"], entry["retry"], entry.get("rerun_reason")) for entry in report["missing"]] == [(3, 1, None)]


@pytest.mark.parametrize("change, reason", [
    ({"checks_hash": "sha256:" + "1" * 64}, "The instruction changed."),
    ({"checks_inputs": {"@artifacts": ["/workspace"]}}, "The saved work lacks the changed artifacts."),
])
def test_old_audit_rows_rerun_when_the_claim_does_not_name_their_checks_or_artifacts(tmp_path, change, reason):
    config, _, row = old_audit_row(tmp_path)
    report = plan([TASK], config, [{**row, **change}], n_attempts=1, saved_work=tmp_path / "cache")
    assert (report["regrade_trials"], [entry["rerun_reason"] for entry in report["missing"]]) == (0, [reason])


def test_a_regraded_old_row_carries_the_current_instruction_and_needs_nothing_more(tmp_path):
    config, _, old = old_audit_row(tmp_path)
    item, = plan([TASK], config, [old], n_attempts=1, saved_work=tmp_path / "cache")["regrades"]
    job = tmp_path / "output/jobs/regrade"
    verifier = job / "0/verifier"
    verifier.mkdir(parents=True)
    (job / "0/agent").mkdir()
    (job / "0/agent/trajectory.json").write_bytes(Path(old["trajectory_file"]).read_bytes())
    (job / "regrade.json").write_text(json.dumps([item]))
    (job / "0/regrade-finished.json").write_text(json.dumps("2026-11-25T12:00:00Z"))
    judge = {"agent": "claude-code", "model": config.judge.model, "reasoning_effort": config.judge.effort}
    (verifier / "reward.json").write_text('{"reward": 0.0}')
    (verifier / "reward-details.json").write_text(json.dumps({
        "report": {"kind": "programmatic", "criteria": [{"name": "report_written", "value": 1, "reasoning": "A report."}]},
        "lookup": {"kind": "agent", "judge": judge, "criteria": [
            {"name": "no_audit_lookup", "value": 0, "raw": "no", "reasoning": "Step 9 downloads the audit report."}]}}))
    row, = recover_regrades(tmp_path / "output")
    assert (row["status"], row["checks"]["no_audit_lookup"]["passed"], row["instruction_hash"]) == (
        "failed", False, item["instruction_hash"])
    assert trial_identity(row) == trial_identity(item) != trial_identity(old)
    rows = fold_rows([old], [row])
    assert plan([TASK], config, rows, n_attempts=1, saved_work=tmp_path / "cache")["missing"] == []


def redo_entry(row, **changes):
    return {**{key: row[key] for key in ("task_id", "agent", "model", "effort", "mode", "trial", "completed_at")},
            "reason": "Looked up the published report.", **changes}


def test_a_redo_entry_plans_one_fresh_trial_until_a_newer_row_lands(tmp_path):
    task, config, row = saved_trial(tmp_path)
    row = {**row, "retry": 1}
    report = plan([task], config, [row, {**row, "trial": 2}], n_attempts=2, redo=[redo_entry(row)])
    redo, = report["missing"]
    assert (redo["trial"], redo["retry"], redo["rerun_reason"]) == (1, 0, "On the redo list: Looked up the published report.")
    fresh = {**row, "retry": redo["retry"], "checks_generation": redo["checks_generation"],
             "completed_at": "2026-12-01T00:00:00+00:00"}
    rows = fold_rows([row, {**row, "trial": 2}], [fresh])
    assert fresh in rows
    assert plan([task], config, rows, n_attempts=2, redo=[redo_entry(row)])["missing"] == []


def test_the_redo_list_needs_a_finished_trial(tmp_path):
    _, _, row = saved_trial(tmp_path)
    path = tmp_path / "redo.json"
    path.write_text(json.dumps([redo_entry(row, completed_at=None)]))
    with pytest.raises(ValueError, match="completed_at"):
        read_redo(path)
    path.write_text(json.dumps([redo_entry(row)] * 2))
    with pytest.raises(ValueError, match="twice"):
        read_redo(path)
    assert read_redo(tmp_path / "absent.json") == []
    assert isinstance(read_redo(ROOT / "runner/redo.json"), list)


def test_the_lookup_copy_keeps_tool_calls_and_outputs_and_drops_messages_and_reasoning(tmp_path):
    trajectory = {"schema_version": "ATIF-v1.7", "steps": [
        {"step_id": 1, "source": "user", "message": "INSTRUCTION-TEXT"},
        {"step_id": 2, "source": "agent", "message": "MESSAGE-TEXT", "reasoning_content": "REASONING-TEXT",
         "tool_calls": [{"tool_call_id": "call-1", "function_name": "bash",
                         "arguments": {"command": "curl -sL https://example.org/audits/Audit.pdf"}}],
         "observation": {"results": [{"source_call_id": "call-1",
                                      "content": [{"type": "text", "text": "PDF-SAVED"}, {"type": "image"}]}]}},
        {"step_id": 3, "source": "agent", "message": "FINAL-TEXT", "reasoning_content": "MORE-REASONING"},
    ]}
    source = tmp_path / "trajectory.json"
    source.write_text(json.dumps(trajectory))
    target = tmp_path / "lookup/trajectory.txt"
    helper().main(source, target, TASK / "tests")
    record = target.read_text()
    assert "curl -sL https://example.org/audits/Audit.pdf" in record and "PDF-SAVED" in record
    assert "call-1" in record and "## Step 2" in record
    for hidden in ("INSTRUCTION-TEXT", "MESSAGE-TEXT", "REASONING-TEXT", "FINAL-TEXT", "MORE-REASONING"):
        assert hidden not in record


@pytest.mark.parametrize("content", [None, "not json", '{"steps": "none"}'])
def test_an_unreadable_trajectory_leaves_no_reward_so_the_trial_is_an_error(tmp_path, monkeypatch, content):
    source = tmp_path / "trajectory.json"
    if content is not None:
        source.write_text(content)
    output = tmp_path / "verifier"
    output.mkdir()
    (output / "reward.json").write_text('{"reward": 1.0}')
    monkeypatch.setenv("REWARDKIT_LOG_DIR", str(output))
    with pytest.raises(SystemExit):
        helper().main(source, tmp_path / "lookup/trajectory.txt", TASK / "tests")
    assert not (output / "reward.json").exists()
    assert "cannot read the trajectory" in (output / "judge-error.txt").read_text()
    assert not (tmp_path / "lookup").exists()


def test_without_the_lookup_judge_no_trajectory_is_needed(tmp_path):
    helper().main(tmp_path / "absent.json", tmp_path / "lookup/trajectory.txt", tmp_path)
    assert not (tmp_path / "lookup").exists()
