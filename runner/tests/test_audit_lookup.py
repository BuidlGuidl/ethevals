import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from ethevals.harbor_tasks import lint_claim
from ethevals.job_config import JudgeSettings, load_job
from ethevals.jobs import decide_saved_row, plan, read_redo, task_entry
from ethevals.regrade import regrade_options
from ethevals.trial_rows import fold_rows, recover_regrades, results_row, trial_identity
from support import recorded_trial
from test_jobs import job_config
from test_regrade import saved_trial

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks/build/audit-the-compact"
CLAIM = json.loads((TASK / "tests/regrade-from.json").read_text())
OLD_INSTRUCTION, = CLAIM["instructions"]


def helper():
    spec = importlib.util.spec_from_file_location("audit_agent_judge", TASK / "tests/agent_judge.py")
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
    row.update(status="passed", instruction_hash=OLD_INSTRUCTION, checks_hash=CLAIM["checks"][0],
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


def test_old_audit_rows_without_a_named_checks_hash_get_fresh_trials(tmp_path):
    config, _, row = old_audit_row(tmp_path)
    report = plan([TASK], config, [{**row, "checks_hash": "sha256:" + "1" * 64}], n_attempts=1,
                  saved_work=tmp_path / "cache")
    assert (report["regrade_trials"], [(entry["retry"], entry.get("rerun_reason")) for entry in report["missing"]]) == (
        0, [(0, None)])


def test_old_audit_rows_rerun_when_the_claim_does_not_name_their_artifacts(tmp_path):
    config, _, row = old_audit_row(tmp_path)
    report = plan([TASK], config, [{**row, "checks_inputs": {"@artifacts": ["/workspace"]}}], n_attempts=1,
                  saved_work=tmp_path / "cache")
    assert [entry["rerun_reason"] for entry in report["missing"]] == ["The saved work lacks the changed artifacts."]


def edited_task(tmp_path, name, line):
    """A scratch copy of the-compact with one more line in one file."""
    task = tmp_path / "tasks/build/audit-the-compact"
    shutil.copytree(TASK, task, ignore=shutil.ignore_patterns("__pycache__"))
    (task / name).write_text((task / name).read_text() + line)
    return task


def test_a_later_instruction_edit_reruns_instead_of_carrying_and_lint_names_the_stale_claim(tmp_path):
    config, item, old = old_audit_row(tmp_path)
    current = {**old, "instruction_hash": item["instruction_hash"], "checks_hash": item["checks_hash"],
               "checks_inputs": item["checks_inputs"], "completed_at": "2026-12-01T00:00:00+00:00"}
    task = edited_task(tmp_path, "instruction.md", "\nAlso check the deploy scripts.\n")
    report = plan([task], config, [old, current], n_attempts=1, saved_work=tmp_path / "cache")
    assert (report["regrade_trials"], [(entry["retry"], entry["instruction_hash"]) for entry in report["missing"]]) == (
        0, [(0, task_entry(task, config)["instruction_hash"])])
    with pytest.raises(ValueError, match="remove or update the claim"):
        lint_claim(task)


def test_a_row_on_the_current_instruction_wins_over_the_carried_old_row_and_its_redo_fires_once(tmp_path):
    config, item, old = old_audit_row(tmp_path)
    redone = {**old, "instruction_hash": item["instruction_hash"], "checks_hash": item["checks_hash"],
              "checks_inputs": item["checks_inputs"], "completed_at": "2026-12-01T00:00:00+00:00",
              "checks_generation": 1, "retry": 0}
    report = plan([TASK], config, [old, redone], n_attempts=1, redo=[redo_entry(old)], saved_work=tmp_path / "cache")
    assert (report["missing"], report["regrades"]) == ([], [])


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


def test_the_plan_lists_redo_entries_that_match_no_saved_row(tmp_path):
    task, config, row = saved_trial(tmp_path)
    typo = redo_entry({**row, "trial": 2}, completed_at="2026-01-01T00:00:00Z")
    report = plan([task], config, [row, {**row, "trial": 2}], n_attempts=2,
                  redo=[redo_entry(row), typo, redo_entry({**row, "task_id": "concepts/other"})])
    assert (len(report["missing"]), report["redo_unmatched"]) == (1, [typo])


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


def lookup_copy(tmp_path, trajectory, monkeypatch):
    source = tmp_path / "trajectory.json"
    source.write_text(json.dumps(trajectory))
    monkeypatch.setenv("REWARDKIT_LOG_DIR", str(tmp_path / "verifier"))
    (tmp_path / "verifier").mkdir(exist_ok=True)
    helper().prepare_lookup(source, tmp_path / "lookup", TASK / "tests")
    return (tmp_path / "lookup/trajectory.txt").read_text()


def step(number, *calls, results=(), **extra):
    return {"step_id": number, "source": "agent", "message": f"MESSAGE-{number}", "reasoning_content": f"REASONING-{number}",
            "tool_calls": list(calls), "observation": {"results": list(results)}, **extra}


def test_the_lookup_copy_keeps_tool_calls_and_outputs_and_drops_messages_and_reasoning(tmp_path, monkeypatch):
    search = {"tool_call_id": "call-2", "function_name": "web_search",
              "arguments": {"queries": [{"q": "the compact audit report", "text": "shown"}]}}
    child = {"schema_version": "ATIF-v1.7", "trajectory_id": "child-1", "agent": {"name": "sub", "version": "1"},
             "steps": [step(1, search, results=[{"source_call_id": "call-2", "content": "CHILD-RESULT"}])]}
    trajectory = {"schema_version": "ATIF-v1.7", "agent": {"name": "agent", "version": "1"}, "subagent_trajectories": [child], "steps": [
        {"step_id": 1, "source": "user", "message": "INSTRUCTION-TEXT"},
        step(2, {"tool_call_id": "call-1", "function_name": "bash",
                 "arguments": {"command": "curl -sL https://example.org/audits/Audit.pdf"}},
             results=[{"source_call_id": "call-1", "content": [{"type": "text", "text": "PDF-SAVED"}, {"type": "image"}]},
                      {"source_call_id": "task-1", "content": "Delegated.", "subagent_trajectory_ref": [{"trajectory_id": "child-1"}]}]),
        {"step_id": 3, "source": "agent", "message": "FINAL-TEXT", "reasoning_content": "MORE-REASONING"},
    ]}
    record = lookup_copy(tmp_path, trajectory, monkeypatch)
    assert "curl -sL https://example.org/audits/Audit.pdf" in record and "PDF-SAVED" in record
    assert json.dumps(search["arguments"]) in record and "CHILD-RESULT" in record
    for hidden in ("INSTRUCTION-TEXT", "MESSAGE-", "REASONING-", "FINAL-TEXT", "MORE-REASONING"):
        assert hidden not in record
    manifest = json.loads((tmp_path / "verifier/judge-inputs-lookup.json").read_text())
    assert list(manifest) == ["trajectory.txt"]


@pytest.mark.parametrize("trajectory", [
    None, "not json", {"steps": "none"}, {"steps": []},
    {"steps": [step(1)], "continued_trajectory_ref": "trajectory.cont-1.json"},
    {"steps": [step(1, results=[{"source_call_id": "t", "content": "x",
                                 "subagent_trajectory_ref": [{"trajectory_path": "child.json"}]}])]},
])
def test_an_unreadable_or_incomplete_trajectory_leaves_no_reward_so_the_trial_is_an_error(tmp_path, monkeypatch, trajectory):
    source = tmp_path / "trajectory.json"
    if trajectory is not None:
        source.write_text(trajectory if isinstance(trajectory, str) else json.dumps(trajectory))
    output = tmp_path / "verifier"
    output.mkdir()
    (output / "reward.json").write_text('{"reward": 1.0}')
    monkeypatch.setenv("REWARDKIT_LOG_DIR", str(output))
    with pytest.raises(SystemExit):
        helper().prepare_lookup(source, tmp_path / "lookup", TASK / "tests")
    assert not (output / "reward.json").exists()
    assert "cannot read the trajectory" in (output / "judge-error.txt").read_text()
    assert not (tmp_path / "lookup").exists()


def test_without_the_lookup_judge_no_trajectory_is_needed(tmp_path):
    helper().prepare_lookup(tmp_path / "absent.json", tmp_path / "lookup", tmp_path)
    assert not (tmp_path / "lookup").exists()


def test_the_audit_judges_cannot_read_the_raw_trajectory():
    settings = json.loads((TASK / "tests/judge-settings.json").read_text())
    assert "Read(//logs/agent/**)" in settings["permissions"]["deny"]


@pytest.mark.parametrize("name", ["tests/lookup-prompt.md", "tests/agent_judge.py"])
def test_changing_the_lookup_prompt_or_its_input_preparation_plans_a_judge_regrade(tmp_path, name):
    config = load_job(job_config(tmp_path, "free"))
    config.judge = JudgeSettings()
    before = task_entry(TASK, config)
    task = edited_task(tmp_path, name, "\n# A clarification.\n")
    current = {**task_entry(task, config), "regrade": regrade_options(task)}
    row = {**before, "status": "passed", "retry": 0}
    assert decide_saved_row(row, current, config.retry) == {"action": "regrade", "kind": "judge", "judge_required": True}


def test_a_changed_lookup_copy_asks_only_the_lookup_judge_again(tmp_path, monkeypatch):
    import rewardkit.reward
    from rewardkit.models import JudgeResult, Score
    from rewardkit.runner import run as rewardkit_run
    from ethevals.regrade_checks import replay

    calls = []

    async def fake_agent(judge, criteria, weights=None, workspace=None, system_prompt=None):
        calls.append(judge.cwd)
        return JudgeResult([Score(name=c.name, value=1.0, raw="yes", reasoning="Judged.", description=c.description)
                            for c in criteria], "", [], guard=Score(name="guard", value=0.0, raw="no", reasoning="None."))
    monkeypatch.setattr(rewardkit.reward, "arun_agent", fake_agent)
    tests = tmp_path / "tests"
    shutil.copytree(TASK / "tests", tests, ignore=shutil.ignore_patterns("__pycache__"))
    source, current = tmp_path / "source", tmp_path / "current"
    rewardkit_run(tests, workspace=tmp_path, output=source / "saved-verifier/reward.json", yolo=True)
    assert sorted(calls) == ["/judge", "/lookup"]
    for folder in (source / "saved-verifier", current):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "judge-inputs.json").write_text('{"findings.md": "same"}\n')
        (folder / "judge-inputs-lookup.json").write_text('{"trajectory.txt": "old"}\n')
    item = {"source_row": {"checks_inputs": {}}, "checks_inputs": {}, "judge_required": True}
    (tmp_path / "item.json").write_text(json.dumps(item))
    monkeypatch.setenv("ETHEVALS_REGRADE_ITEM", str(tmp_path / "item.json"))
    monkeypatch.setenv("ETHEVALS_REGRADE_SOURCE", str(source))
    monkeypatch.setenv("REWARDKIT_LOG_DIR", str(current))
    calls.clear()
    replay(tests, workspace=tmp_path, output=current / "unchanged/reward.json")
    assert calls == []
    (current / "judge-inputs-lookup.json").write_text('{"trajectory.txt": "new"}\n')
    replay(tests, workspace=tmp_path, output=current / "changed/reward.json")
    assert calls == ["/lookup"]

