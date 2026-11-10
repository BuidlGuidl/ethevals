import asyncio
import json

from harbor.job import Job
import pytest

from ethevals.job_config import load_job
from ethevals.jobs import budget_check, plan, run
from ethevals.trial_rows import recover_rows
from support import recorded_trial
from test_jobs import job_config, task_folder


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
