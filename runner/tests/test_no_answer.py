import asyncio
import json

from harbor.job import Job
import pytest

from ethevals.job_config import load_job
from ethevals.jobs import budget_check, plan, run
from ethevals.trial_rows import recover_rows
from support import recorded_trial
from test_jobs import job_config, task_folder


def test_converted_empty_reply_rows_record_the_no_answer():
    from pathlib import Path
    rows = [json.loads(line) for line in (Path(__file__).resolve().parents[2] / "results/rows.jsonl").read_text().splitlines()]
    converted = [row for row in rows if row.get("error_kind") == "no_answer"]
    assert len(converted) == 14
    assert [(row["status"], row.get("no_answer")) for row in converted] == [
        ("error", [{"kind": "empty", "stop_reason": None}])] * 14


@pytest.mark.parametrize("unanswered", ["empty", "refused"])
@pytest.mark.parametrize("failure", ["agent_version", "judge", "rewards"])
def test_no_answer_never_hides_an_integrity_error(tmp_path, unanswered, failure):
    from ethevals.trial_rows import results_row
    task = task_folder(tmp_path)
    config = load_job(job_config(tmp_path, "free"))
    item, = plan([task], config, [], n_attempts=1)["missing"]
    item["no_answer"] = [{"kind": unanswered, "stop_reason": None}]
    folder = tmp_path / "saved"
    recorded_trial(folder, task)
    trajectory = folder / "agent/trajectory.json"
    data = json.loads(trajectory.read_text())
    data["steps"][-1]["message"] = ""
    trajectory.write_text(json.dumps(data))
    result_path = folder / "result.json"
    result = json.loads(result_path.read_text())
    if unanswered == "refused":
        result["exception_info"] = {"exception_type": "AgentSafetyRefusalError", "exception_message": "Refused.",
                                    "exception_traceback": "", "occurred_at": result["finished_at"]}
    if failure == "agent_version":
        item["agent_version"] = "wrong"
    elif failure == "judge":
        item["judge"] = {"model": "openai/planned", "effort": "high"}
    else:
        result["verifier_result"]["rewards"] = {"reward": 0.0}
    result_path.write_text(json.dumps(result))
    row = results_row(folder, item)
    assert (row["status"], row["error_kind"]) == ("error", "verification" if failure == "rewards" else failure)


def test_second_ask_never_uses_a_previous_ci_runs_row(tmp_path, monkeypatch):
    task = task_folder(tmp_path)
    config = load_job(job_config(tmp_path, "free"))
    first, = plan([task], config, [], n_attempts=1)["missing"]
    previous = {**first, "status": "error", "error_kind": "no_answer", "schema_version": 8,
                "no_answer": [{"kind": "empty", "stop_reason": None}], "completed_at": "2026-11-09T00:00:00Z"}
    report = budget_check(plan([task], config, [previous], n_attempts=1), 0)
    calls = []

    async def no_result(job):
        calls.append(job)

    monkeypatch.setattr(Job, "run", no_result)
    assert asyncio.run(run(report, config, tmp_path / "out", [previous])) is False
    assert len(calls) == 1


@pytest.mark.parametrize("bare", [False, True])
@pytest.mark.parametrize("first", ["empty", "refused", "content_filter"])
@pytest.mark.parametrize("second", ["answer", "empty", "refused", "content_filter", "crash", "interrupted"])
def test_no_answer_gets_one_immediate_retry(tmp_path, monkeypatch, bare, first, second):
    config = load_job(job_config(tmp_path, "free"))
    task = task_folder(tmp_path)
    if bare:
        config.agents["local"].name = "ethevals.vanilla:VanillaAgent"
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    output = tmp_path / "out"
    calls = []

    async def fake_run(job):
        state = first if not calls else second
        calls.append(state)
        if state == "interrupted":
            raise RuntimeError("The CI job stopped.")
        folder = job.job_dir / "trial"
        recorded_trial(folder, task)
        result_path = folder / "result.json"
        result = json.loads(result_path.read_text())
        result["finished_at"] = f"2026-11-10T10:00:0{len(calls)}+00:00"
        if state in {"refused", "crash", "content_filter"}:
            result["exception_info"] = {
                "exception_type": "RuntimeError" if state == "crash" else "AgentSafetyRefusalError",
                "exception_message": "The agent stopped.", "exception_traceback": "",
                "occurred_at": result["finished_at"],
            }
        result_path.write_text(json.dumps(result))
        trajectory_path = folder / "agent/trajectory.json"
        trajectory = json.loads(trajectory_path.read_text())
        trajectory["steps"][-1]["message"] = {"answer": "metre", "refused": "I can't help with that."}.get(state, "")
        trajectory_path.write_text(json.dumps(trajectory))
        stop = "content_filter" if state == "content_filter" else "stop"
        if state != "refused":
            (folder / "agent/provider.json").write_text(json.dumps({
                "stop_reason": stop, "refused": state == "content_filter"}))

    monkeypatch.setattr(Job, "run", fake_run)
    if second == "interrupted":
        with pytest.raises(RuntimeError, match="CI job stopped"):
            asyncio.run(run(report, config, output, []))
    else:
        assert asyncio.run(run(report, config, output, [])) == (second != "crash")
    row, = recover_rows(output)
    assert calls == [first, second]
    assert (row["trial"], row["retry"]) == (1, 0)
    assert row["no_answer"][0] == {
        "kind": "empty" if first == "empty" else "refused",
        "stop_reason": "content_filter" if first == "content_filter" else
                       "AgentSafetyRefusalError" if first == "refused" else "stop",
    }
    if second == "answer":
        assert (row["status"], row["error_kind"], row["checks"]) == (
            "passed", None, {"unit": {"passed": True, "reason": "The final reply matches."}})
    elif second in {"empty", "refused", "content_filter"}:
        assert (row["status"], row["rewards"], row["checks"], row["no_answer"][-1]) == (
            "failed", {"reward": 0.0}, {"no_answer": {"passed": False, "reason": "No answer twice."}},
            {"kind": "empty" if second == "empty" else "refused",
             "stop_reason": "stop" if second == "empty" else
                            "content_filter" if second == "content_filter" else "AgentSafetyRefusalError"})
    else:
        assert (row["status"], row["error_kind"]) == (
            "error", "no_answer" if second == "interrupted" else "RuntimeError")
        retry, = plan([task], config, [row], n_attempts=1)["missing"]
        assert (retry["trial"], retry["retry"], retry["worst_case_usd"]) == (1, 1, 0)
