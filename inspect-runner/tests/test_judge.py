import asyncio
import json
from pathlib import Path
import shutil

import litellm
import pytest

from test_jobs import job_config, task_folder


def recorded_trial(tmp_path):
    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    trial = tmp_path / "trial"
    shutil.copytree(fixture, trial)
    return trial, json.loads((fixture / "board.json").read_text())


def test_recorded_trial_criteria_reach_rows_with_reason_and_judge(tmp_path, monkeypatch):
    from ethevals.judge import JudgeSettings, judge_trial
    from ethevals.trial_rows import results_row

    trial, metadata = recorded_trial(tmp_path)
    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## Explained the unit?\nDid the reply explain the unit?\n")
    with (task / "task.toml").open("a") as file:
        file.write('\n[[artifacts]]\nsource = "/app/note.txt"\ndestination = "note.txt"\n')
    (trial / "artifacts").mkdir()
    (trial / "artifacts/note.txt").write_text("A metre measures length.")
    requests = []

    async def completion(**kwargs):
        requests.append(kwargs)
        response = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content":
            '{"score":"no","reasoning":"The reply names the unit without an explanation."}'}}],
            usage={"prompt_tokens": 100, "completion_tokens": 10})
        response._hidden_params["response_cost"] = 0.0123
        return response

    monkeypatch.setattr(litellm, "acompletion", completion)
    settings = JudgeSettings(model="openai/gpt-5", paid_by="free")
    metadata.update(judge={"model": settings.model, "effort": settings.effort},
                    criteria_names=["Explained the unit?"])
    asyncio.run(judge_trial(trial, task, settings))
    row = results_row(trial, metadata)
    assert (row["status"], row["judge"], row["judge_paid_by"], row["judge_cost_usd"]) == (
        "failed", {"model": "openai/gpt-5", "effort": "high"}, "free", 0)
    assert row["checks"] == {
        "unit": {"passed": True, "reason": "The final reply matches."},
        "Explained the unit?": {"passed": False, "reason": "The reply names the unit without an explanation."}}
    assert len(requests) == 1
    request = requests[0]
    assert (request["model"], request["reasoning_effort"]) == ("openai/gpt-5", "high")
    assert "Did the reply explain the unit?" in request["messages"][0]["content"]
    evidence = json.dumps(request["messages"][1]["content"])
    assert "metre" in evidence and "A metre measures length." in evidence
    saved = json.loads((trial / "verifier/judge.json").read_text())
    assert saved["usage"]["cost_usd"] == 0.0123
    # Recovery never sends a second request for this attempt.
    asyncio.run(judge_trial(trial, task, settings))
    assert results_row(trial, metadata)["checks"] == row["checks"]
    assert len(requests) == 1


@pytest.mark.parametrize("reply", ["timeout", "deadline", "not JSON", '{"score":"perhaps","reasoning":"Unclear."}',
                                   '{"score":"yes"}'])
def test_judge_errors_reach_rows_and_planner_retries(tmp_path, monkeypatch, reply):
    from ethevals.judge import JudgeSettings, judge_trial
    from ethevals.jobs import budget_check, load_job, plan, task_entry
    from ethevals.trial_rows import previous_rows

    trial, metadata = recorded_trial(tmp_path)
    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path, "free"))
    config.agents["local"].name = "oracle"
    config.judge = JudgeSettings(model="openai/gpt-5", paid_by="free", time_limit=1)
    planned = plan([task], config, [], trials=1)
    metadata = {**planned["missing"][0], "task_hash": task_entry(task)["hash"]}

    async def completion(**kwargs):
        if reply == "deadline":
            await asyncio.sleep(10)
        if reply == "timeout":
            raise litellm.Timeout(message="The stand-in timed out.", model=kwargs["model"], llm_provider="openai")
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": reply}}])

    monkeypatch.setattr(litellm, "acompletion", completion)
    asyncio.run(judge_trial(trial, task, config.judge))
    job = tmp_path / "out/jobs/recorded"
    shutil.copytree(trial, job / "trial")
    (job / "board.json").write_text(json.dumps(metadata))
    rows = previous_rows(tmp_path / "out", tmp_path / "none")
    assert (rows[0]["status"], rows[0]["error_kind"], rows[0]["checks"]) == (
        "error", "judge", {"unit": {"passed": True, "reason": "The final reply matches."}})
    assert rows[0]["error_reason"].startswith("Cannot judge criteria:")
    again = budget_check(plan([task], config, rows, trials=1), 0)
    assert [(item["trial"], item["attempt"]) for item in again["missing"]] == [(1, 2)]


def test_criteria_judge_reserves_api_spend_for_a_plan_funded_agent(tmp_path, monkeypatch):
    from ethevals.jobs import budget_check, load_job, plan, run

    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path))
    report = budget_check(plan([task], config, [], trials=1), 0)
    item = report["missing"][0]
    assert (item["agent_reserve_usd"], item["judge_reserve_usd"], item["worst_case_usd"]) == (0, 2, 4)
    assert item["judge"] == {"model": "anthropic/claude-opus-5-5", "effort": "high"}
    with pytest.raises(ValueError, match="Budget exceeded"):
        asyncio.run(run(report, config, tmp_path / "out", []))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="judge requires ANTHROPIC_API_KEY"):
        asyncio.run(run(budget_check(report, 4), config, tmp_path / "out", []))
    assert not (tmp_path / "out/jobs").exists()


def test_multiple_criteria_keep_names_reasons_and_api_price_cost(tmp_path, monkeypatch):
    from ethevals.judge import JudgeSettings, judge_trial
    from ethevals.trial_rows import results_row

    trial, metadata = recorded_trial(tmp_path)
    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text(
        "## A unit was named\nDid the reply name a unit?\n\n## Length?\nDoes the unit measure length?\n")
    metadata.update(judge={"model": "anthropic/claude-opus-5-5", "effort": "high"},
                    criteria_names=["A unit was named", "Length?"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stand-in-api-key")
    monkeypatch.delenv("REWARDKIT_FORCE_SUBSCRIPTION", raising=False)

    async def completion(**kwargs):
        assert kwargs["model"] == "anthropic/claude-opus-5-5"
        response = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": json.dumps({
            "q_0": {"score": "yes", "reasoning": "The reply says metre."},
            "q_1": {"score": "yes", "reasoning": "A metre measures length."}})}}])
        response._hidden_params["response_cost"] = 0.0123
        return response

    monkeypatch.setattr(litellm, "acompletion", completion)
    asyncio.run(judge_trial(trial, task, JudgeSettings()))
    row = results_row(trial, metadata)
    assert (row["status"], row["judge_paid_by"], row["judge_cost_usd"]) == ("passed", "api_key", 0.0123)
    assert row["checks"] == {
        "unit": {"passed": True, "reason": "The final reply matches."},
        "A unit was named": {"passed": True, "reason": "The reply says metre."},
        "Length?": {"passed": True, "reason": "A metre measures length."}}


def test_missing_judge_result_is_a_retryable_error(tmp_path):
    from ethevals.trial_rows import results_row

    trial, metadata = recorded_trial(tmp_path)
    metadata.update(judge={"model": "anthropic/claude-opus-5-5", "effort": "high"}, criteria_names=["explained"])
    row = results_row(trial, metadata)
    assert (row["status"], row["error_kind"], row["checks"]) == (
        "error", "judge", {"unit": {"passed": True, "reason": "The final reply matches."}})
    assert "judge.json" in row["error_reason"]


@pytest.mark.parametrize("key,forced", [("", ""), ("sk-ant-oat-stand-in", ""), ("stand-in-api-key", " true ")])
def test_live_judge_refuses_missing_keys_and_plan_tokens_before_calls(tmp_path, monkeypatch, key, forced):
    from ethevals.jobs import budget_check, load_job, plan, run

    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    monkeypatch.setenv("REWARDKIT_FORCE_SUBSCRIPTION", forced)
    with pytest.raises(ValueError, match="judge requires ANTHROPIC_API_KEY"):
        asyncio.run(run(budget_check(plan([task], config, [], trials=1), 4), config, tmp_path / "out", []))
    assert not (tmp_path / "out/jobs").exists()


@pytest.mark.docker
def test_job_runs_rewardkit_with_a_local_http_judge_and_recovers_criteria(tmp_path, monkeypatch):
    from ethevals.jobs import budget_check, load_job, plan, run
    from support import cli
    from test_vanilla import stand_in

    task = tmp_path / "question"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/question", task)
    (task / "tests/criteria.md").write_text("## named_unit\nDid the reply name a unit?\n")
    declaration = task / "task.toml"
    declaration.write_text(declaration.read_text().replace(
        'artifacts = ["/logs/agent/trajectory.json"]',
        'artifacts = ["/logs/agent/trajectory.json", {source = "/note.txt", destination = "note.txt"}]'))
    solution = task / "solution/solve.sh"
    solution.write_text(solution.read_text() + '\nprintf "A metre measures length.\\n" > /note.txt\n')
    config = job_config(tmp_path, "free")
    data = json.loads(config.read_text())
    data["trials"] = 1
    data["agents"]["local"]["name"] = "oracle"
    data["judge"] = {"model": "openai/gpt-5", "paid_by": "free"}
    config.write_text(json.dumps(data))
    output = tmp_path / "out"
    args = ["--config", config, "--tasks", task, "--output", output, "--rows", tmp_path / "none"]
    with stand_in(reply='{"score":"yes","reasoning":"The reply names the unit metre."}') as (completion, requests):
        monkeypatch.setenv("OPENAI_API_BASE", completion["api_base"])
        monkeypatch.setenv("OPENAI_API_KEY", completion["api_key"])
        settings = load_job(config)
        success = asyncio.run(run(budget_check(plan([task], settings, []), 0), settings, output, []))
        assert success is True, (output / "rows.jsonl").read_text()
        row = json.loads((output / "rows.jsonl").read_text())
        assert (row["status"], row["judge"], row["judge_paid_by"], row["judge_cost_usd"]) == (
            "passed", {"model": "openai/gpt-5", "effort": "high"}, "free", 0)
        assert row["checks"] == {
            "unit": {"passed": True, "reason": "The final reply matches."},
            "named_unit": {"passed": True, "reason": "The reply names the unit metre."}}
        assert len(requests) == 1
        assert requests[0]["model"] == "gpt-5"
        assert "A metre measures length." in json.dumps(requests[0]["messages"])
        assert requests[0]["response_format"]["json_schema"]["strict"] is True
        (output / "rows.jsonl").unlink()
        resumed = cli("-m", "ethevals.cli", "run", *args)
        assert resumed.returncode == 0, resumed.stdout + resumed.stderr
        assert json.loads((output / "rows.jsonl").read_text()) == row
        assert len(requests) == 1
