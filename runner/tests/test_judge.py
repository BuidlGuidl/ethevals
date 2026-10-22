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


@pytest.mark.parametrize("retry,judge_attempts,expected", [
    (0, 2, 1), (0, 0, 1), (1, 2, None), (1, 0, None),
])
def test_ci_judge_error_without_a_local_folder_uses_agent_retry_rules(
    tmp_path, retry, judge_attempts, expected,
):
    from ethevals.job_config import load_job
    from ethevals.jobs import plan

    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid it explain the unit?\n")
    config = load_job(job_config(tmp_path, "api_key"))
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    row = {**item, "status": "error", "error_kind": "judge", "retry": retry,
           "judge_attempts": judge_attempts, "verifier_files": "/home/runner/work/old/trial/verifier"}
    report = plan([task], config, [row], n_attempts=1)
    assert [entry["retry"] for entry in report["missing"]] == ([] if expected is None else [expected])
    if expected:
        assert report["missing"][0]["agent_reserve_usd"] == 3
    else:
        assert [entry["retry"] for entry in report["exhausted_errors"]] == [1]


def test_published_interrupted_judge_retries_agent_after_artifact_moves(tmp_path):
    from ethevals.job_config import load_job
    from ethevals.jobs import plan
    from ethevals.publish import publish_logs
    from ethevals.trial_rows import recover_rows

    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid it explain the unit?\n")
    config = load_job(job_config(tmp_path, "api_key"))
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    folder = tmp_path / "out/jobs/saved/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    (folder.parent / "board.json").write_text(json.dumps(item))
    rows = recover_rows(tmp_path / "out")
    assert (rows[0]["error_kind"], rows[0]["judge_attempts"]) == ("judge", 0)
    published = publish_logs(tmp_path / "release", "owner/repo", "16", "a" * 40, rows=rows)
    shutil.move(str(tmp_path / "out"), tmp_path / "downloaded")
    report = plan([task], config, published["rows"], n_attempts=1)
    assert [(entry["retry"], entry["agent_reserve_usd"]) for entry in report["missing"]] == [(1, 3)]
    assert len(published["assets"]) == 2


@pytest.mark.parametrize("changed", ["judge", "collision"])
def test_changed_judge_and_colliding_check_do_not_abort_or_loop_the_plan(tmp_path, monkeypatch, changed):
    from harbor.job import Job
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run
    from ethevals.judge import JudgeSettings
    from ethevals.trial_rows import recover_rows

    task = task_folder(tmp_path)
    heading = "unit" if changed == "collision" else "explained"
    (task / "tests/criteria.md").write_text(f"## {heading}\nDid it explain the unit?\n")
    config = load_job(job_config(tmp_path, "free"))
    config.agents["local"].name = "oracle"
    config.judge = JudgeSettings(model="openai/gpt-5", paid_by="free")
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    folder = tmp_path / "old/jobs/saved/trial"
    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    shutil.copytree(fixture, folder)
    (folder.parent / "board.json").write_text(json.dumps(item))
    (folder / "verifier/judge.json").write_text(json.dumps({
        "judge": item["judge"], "paid_by": "free", "cost_usd": 0, "attempts": 1,
        "error": None if changed == "collision" else "Try again.",
        "checks": {heading: {"passed": True, "reason": "The reply explains it."}}}))
    rows = recover_rows(tmp_path / "old")
    if changed == "collision":
        assert rows[0]["error_kind"] == "verification"
    else:
        config.judge.effort = "low"
    calls = []

    async def finished(job):
        calls.append(job.config.tasks[0].path)
        shutil.copytree(fixture, job.job_dir / "trial")

    async def completion(**kwargs):
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content":
            '{"score":"yes","reasoning":"The reply explains it."}'}}])

    monkeypatch.setattr(Job, "run", finished)
    monkeypatch.setattr(litellm, "acompletion", completion)
    report = budget_check(plan([task], config, rows, n_attempts=2), 0)
    assert [(entry["trial"], entry["retry"]) for entry in report["missing"]] == [(1, 1), (2, 0)]
    asyncio.run(run(report, config, tmp_path / "new", rows))
    assert calls == [task.resolve(), task.resolve()]
    next_plan = plan([task], config, recover_rows(tmp_path / "new"), n_attempts=1)
    assert next_plan["missing"] == []
    assert len(next_plan["exhausted_errors"]) == int(changed == "collision")


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
    # Recovery never sends a second request for this retry.
    asyncio.run(judge_trial(trial, task, settings))
    assert results_row(trial, metadata)["checks"] == row["checks"]
    assert len(requests) == 1


@pytest.mark.parametrize("reply", ["timeout", "deadline", "not JSON", '{"score":"perhaps","reasoning":"Unclear."}',
                                   '{"score":"yes"}'])
def test_judge_errors_retry_only_judging_and_stop_at_the_judge_limit(tmp_path, monkeypatch, reply):
    from ethevals.judge import JudgeSettings, judge_trial
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, task_entry
    from ethevals.trial_rows import previous_rows

    trial, metadata = recorded_trial(tmp_path)
    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path, "free"))
    config.agents["local"].name = "oracle"
    config.judge = JudgeSettings(model="openai/gpt-5", paid_by="free", time_limit=1)
    planned = plan([task], config, [], n_attempts=1)
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
    again = budget_check(plan([task], config, rows, n_attempts=1), 0)
    assert [(row["trial"], row["retry"]) for row in again["missing"]] == [(1, 1)]
    assert again["rejudge"] == []
    assert json.loads((trial / "verifier/judge.json").read_text())["attempts"] == 2


@pytest.mark.parametrize("interrupted", [False, True])
@pytest.mark.parametrize("separate_output", [False, True])
def test_saved_trial_retries_judge_and_reaches_board_without_an_agent_run(tmp_path, monkeypatch, interrupted, separate_output):
    from harbor.job import Job
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run
    from ethevals.judge import JudgeSettings
    from ethevals.trial_rows import previous_rows

    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path, "free"))
    config.agents["local"].name = "oracle"
    config.judge = JudgeSettings(model="openai/gpt-5", paid_by="free")
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    folder = tmp_path / "out/jobs/saved/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    (folder.parent / "board.json").write_text(json.dumps(item))
    result_before = (folder / "result.json").read_bytes()
    requests = []

    async def completion(**kwargs):
        requests.append(kwargs)
        if len(requests) == 1:
            if interrupted:
                raise asyncio.CancelledError()
            raise litellm.ServiceUnavailableError(message="Try again.", model=kwargs["model"], llm_provider="openai")
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content":
            '{"score":"yes","reasoning":"The reply explains the unit."}'}}])

    def refuse_agent(*args, **kwargs):
        raise AssertionError("A saved trial cannot run an agent again.")

    monkeypatch.setattr(Job, "create", refuse_agent)
    monkeypatch.setattr(litellm, "acompletion", completion)
    if interrupted:
        from ethevals.judge import judge_trial
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(judge_trial(folder, task, config.judge))
    rows = previous_rows(tmp_path / "out", tmp_path / "none")
    report = budget_check(plan([task], config, rows, n_attempts=1), 0, required=True)
    assert report["missing"] == []
    assert [(entry["retry"], entry["agent_reserve_usd"]) for entry in report["rejudge"]] == [(0, 0)]
    output = tmp_path / "new-out" if separate_output else tmp_path / "out"
    assert asyncio.run(run(report, config, output, rows)) is True
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["status"], row["retry"], row["checks"]["explained"]) == (
        "passed", 0, {"passed": True, "reason": "The reply explains the unit."})
    assert (folder / "result.json").read_bytes() == result_before
    assert len(list((tmp_path / "out/jobs").glob("*/*/result.json"))) == 1
    assert len(requests) == 2
    assert json.loads((folder / "verifier/judge.json").read_text())["attempts"] == 2
    assert plan([task], config, previous_rows(tmp_path / "out", tmp_path / "none"), n_attempts=1)["missing"] == []


def test_judge_retry_costs_add_on_the_same_trial(tmp_path, monkeypatch):
    from ethevals.judge import JudgeSettings, judge_trial
    from ethevals.trial_rows import results_row

    folder, metadata = recorded_trial(tmp_path)
    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    metadata.update(judge={"model": "openai/gpt-5", "effort": "high"}, criteria_names=["explained"])
    requests = []

    async def completion(**kwargs):
        requests.append(kwargs)
        reply = '{"score":"perhaps","reasoning":"Unclear."}' if len(requests) == 1 else '{"score":"yes","reasoning":"It explains the unit."}'
        response = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": reply}}])
        response._hidden_params["response_cost"] = 0.125
        return response

    monkeypatch.setattr(litellm, "acompletion", completion)
    settings = JudgeSettings(model="openai/gpt-5")
    asyncio.run(judge_trial(folder, task, settings))
    row = results_row(folder, metadata)
    assert (row["status"], row["judge_attempts"], row["judge_cost_usd"]) == ("passed", 2, 0.25)
    asyncio.run(judge_trial(folder, task, settings))
    assert len(requests) == 2


def test_judge_waits_before_its_second_attempt(tmp_path, monkeypatch):
    from ethevals.judge import JudgeSettings, judge_trial
    from ethevals.trial_rows import results_row

    folder, metadata = recorded_trial(tmp_path)
    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid it explain the unit?\n")
    metadata.update(judge={"model": "openai/gpt-5", "effort": "high"}, criteria_names=["explained"])
    events = []

    async def wait(delay):
        events.append(("wait", delay))

    async def completion(**kwargs):
        events.append("call")
        if len(events) == 1:
            raise litellm.ServiceUnavailableError(message="Try again.", model="gpt-5", llm_provider="openai")
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content":
            '{"score":"yes","reasoning":"It explains it."}'}}])

    monkeypatch.setattr(asyncio, "sleep", wait)
    monkeypatch.setattr(litellm, "acompletion", completion)
    asyncio.run(judge_trial(folder, task, JudgeSettings(model="openai/gpt-5", paid_by="free")))
    assert events == ["call", ("wait", 2), "call"]
    assert results_row(folder, metadata)["status"] == "passed"


def test_saved_judge_reserves_only_its_remaining_attempt(tmp_path):
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan

    folder, _ = recorded_trial(tmp_path)
    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path, "api_key"))
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    (folder.parent / "board.json").write_text(json.dumps(item))
    row = {**item, "status": "error", "error_kind": "judge", "retry": 1,
           "judge_attempts": 1, "verifier_files": str(folder / "verifier")}
    report = budget_check(plan([task], config, [row], n_attempts=1), 2, required=True)
    assert report["missing"] == []
    saved = report["rejudge"][0]
    assert (saved["retry"], saved["agent_reserve_usd"], saved["judge_reserve_usd"], report["worst_case_usd"], report["within_budget"]) == (
        1, 0, 2, 2, True)


def test_judge_checks_reject_blank_names_like_test_checks(tmp_path):
    from ethevals.trial_rows import results_row

    folder, metadata = recorded_trial(tmp_path)
    judge = {"model": "openai/gpt-5", "effort": "high"}
    metadata.update(judge=judge, criteria_names=[" "])
    (folder / "verifier/judge.json").write_text(json.dumps({
        "judge": judge, "paid_by": "free", "cost_usd": 0, "attempts": 1, "error": None,
        "checks": {" ": {"passed": True, "reason": "Matches."}}}))
    row = results_row(folder, metadata)
    assert (row["status"], row["error_kind"], row["error_reason"]) == (
        "error", "judge", f"Cannot judge criteria: {folder / 'verifier/judge.json'}: Each check needs a name, boolean passed, and one-line reason.")


def test_row_parses_judge_json_once_and_keeps_its_checks(tmp_path, monkeypatch):
    from ethevals.trial_rows import results_row

    folder, metadata = recorded_trial(tmp_path)
    judge_path = folder / "verifier/judge.json"
    judge = {"model": "openai/gpt-5", "effort": "high"}
    metadata.update(judge=judge, criteria_names=["explained"])
    judge_path.write_text(json.dumps({"judge": judge, "paid_by": "free", "cost_usd": 0,
        "attempts": 1, "error": None, "checks": {"explained": {"passed": True, "reason": "It explains it."}}}))
    original = Path.read_text
    reads = []

    def read(path, *args, **kwargs):
        if path == judge_path:
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    row = results_row(folder, metadata)
    assert (row["status"], row["checks"]["explained"]) == ("passed", {"passed": True, "reason": "It explains it."})
    assert reads == [judge_path]


@pytest.mark.parametrize("content", ['{"reward": {"criteria": [{"name": " ", "value": 1, "reasoning": "Matches."}]}}', '{"reward":'])
def test_check_errors_include_the_source_file(tmp_path, content):
    from ethevals.trial_rows import results_row

    folder, metadata = recorded_trial(tmp_path)
    path = folder / "verifier/reward-details.json"
    path.write_text(content)
    row = results_row(folder, metadata)
    assert (row["status"], row["error_kind"]) == ("error", "verification")
    assert str(path) in row["error_reason"]


def test_criteria_judge_reserves_api_spend_for_a_plan_funded_agent(tmp_path, monkeypatch):
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path))
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    item = report["missing"][0]
    assert (item["agent_reserve_usd"], item["judge_reserve_usd"], item["worst_case_usd"]) == (0, 4, 8)
    assert item["judge"] == {"model": "anthropic/claude-opus-5-5", "effort": "high"}
    with pytest.raises(ValueError, match="Budget exceeded"):
        asyncio.run(run(report, config, tmp_path / "out", []))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="judge requires ANTHROPIC_API_KEY"):
        asyncio.run(run(budget_check(report, 8), config, tmp_path / "out", []))
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
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-offline-plan-token")
    monkeypatch.delenv("REWARDKIT_FORCE_SUBSCRIPTION", raising=False)

    async def completion(**kwargs):
        assert kwargs["model"] == "anthropic/claude-opus-5-5"
        assert "api_key" not in kwargs
        import os
        assert os.environ["ANTHROPIC_API_KEY"] == "stand-in-api-key"
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


def test_custom_judge_key_is_rejected_at_config_load_with_a_plan_token_present(tmp_path, monkeypatch):
    from ethevals.job_config import load_job

    path = job_config(tmp_path)
    data = json.loads(path.read_text())
    data["judge"] = {"key_env": "CUSTOM_JUDGE_KEY"}
    path.write_text(json.dumps(data))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CUSTOM_JUDGE_KEY", "offline-custom-key")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-offline-plan-token")
    with pytest.raises(ValueError, match="key_env[\\s\\S]*ANTHROPIC_API_KEY"):
        load_job(path)


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
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    task = task_folder(tmp_path)
    (task / "tests/criteria.md").write_text("## explained\nDid the reply explain the unit?\n")
    config = load_job(job_config(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    monkeypatch.setenv("REWARDKIT_FORCE_SUBSCRIPTION", forced)
    with pytest.raises(ValueError, match="judge requires ANTHROPIC_API_KEY"):
        asyncio.run(run(budget_check(plan([task], config, [], n_attempts=1), 8), config, tmp_path / "out", []))
    assert not (tmp_path / "out/jobs").exists()


@pytest.mark.docker
def test_job_runs_rewardkit_with_a_local_http_judge_and_recovers_criteria(tmp_path, monkeypatch):
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run
    from support import cli
    from test_vanilla import stand_in

    task = tmp_path / "concepts/question"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/concepts/question", task)
    (task / "tests/criteria.md").write_text("## named_unit\nDid the reply name a unit?\n")
    declaration = task / "task.toml"
    declaration.write_text(declaration.read_text().replace(
        'artifacts = ["/logs/agent/trajectory.json"]',
        'artifacts = ["/logs/agent/trajectory.json", {source = "/note.txt", destination = "note.txt"}]'))
    solution = task / "solution/solve.sh"
    solution.write_text(solution.read_text() + '\nprintf "A metre measures length.\\n" > /note.txt\n')
    config = job_config(tmp_path, "free")
    data = json.loads(config.read_text())
    data["n_attempts"] = 1
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
