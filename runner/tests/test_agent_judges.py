import asyncio
import json
from pathlib import Path

import pytest

from ethevals.checks import JudgeError, read_reward
from ethevals.harbor_tasks import lint_task
from ethevals.job_config import JudgeSettings, check_judge_key, load_job
from ethevals.jobs import budget_check, decide_saved_row, plan, run, task_entry
from ethevals.regrade import regrade_options
from test_jobs import job_config, task_folder


def agent_task(tmp_path, *, live=False):
    task = task_folder(tmp_path)
    (task / "task.toml").write_text((task / "task.toml").read_text() +
        '\n[verifier.env]\nCLAUDE_CODE_OAUTH_TOKEN = "${CLAUDE_CODE_OAUTH_TOKEN}"\n')
    (task / "tests/judge.toml").write_text(
        '[judge]\njudge = "claude-code"\nmodel = "anthropic/claude-opus-5-5"\n'
        'cwd = "/judge"\nguard = "flag"\n'
        + ('[[judge.mcp_servers]]\nname = "playwright"\ntransport = "stdio"\ncommand = "true"\n' if live else '')
        + '[scoring]\naggregation = "all-pass"\n[[criterion]]\nname = "explained"\n'
        'description = "Is the unit explained?"\ntype = "binary"\n')
    (task / "tests/reward.toml").write_text('[[reward]]\nname = "reward"\naggregation = "all-pass"\n')
    config = load_job(job_config(tmp_path, "free"))
    config.judge = JudgeSettings()
    return task, config


@pytest.mark.parametrize("live", [False, True])
def test_judge_changes_rerun_only_when_the_task_declares_a_live_session(tmp_path, live):
    task, config = agent_task(tmp_path, live=live)
    before = task_entry(task, config)
    judge = task / "tests/judge.toml"
    judge.write_text(judge.read_text().replace("unit explained?", "unit explained correctly?"))
    current = {**task_entry(task, config), "regrade": regrade_options(task)}
    row = {**before, "status": "passed"}
    assert decide_saved_row(row, current, config.retry) == (
        {"action": "rerun", "reason": "The judge needs a live browser or chain."} if live else
        {"action": "regrade", "kind": "judge", "judge_required": True})


def test_plan_judge_reserves_no_api_spend_and_sends_only_verifier_credentials(tmp_path, monkeypatch):
    from harbor.job import Job

    task, config = agent_task(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "offline-plan-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-api-key")
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    item, = report["missing"]
    assert (item["judge_reserve_usd"], item["judge_paid_by"], item["judge"]) == (
        0, "plan", {"program": "claude-code", "model": "anthropic/claude-opus-5-5", "effort": "high"})
    captured = []

    class Captured(Exception):
        pass

    async def create(settings):
        captured.append((settings.verifier.env, settings.agents[0].env))
        raise Captured

    monkeypatch.setattr(Job, "create", create)
    with pytest.raises(Captured):
        asyncio.run(run(report, config, tmp_path / "out", []))
    assert captured == [({"REWARDKIT_JUDGE": "claude-code", "REWARDKIT_MODEL": "anthropic/claude-opus-5-5",
        "REWARDKIT_REASONING_EFFORT": "high", "REWARDKIT_FORCE_SUBSCRIPTION": "1",
        "ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": ""}, {})]
    check_judge_key(config.judge)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    with pytest.raises(ValueError, match="requires CLAUDE_CODE_OAUTH_TOKEN"):
        check_judge_key(config.judge)


def test_agent_judge_lint_rejects_api_keys_and_prompt_file_attachments(tmp_path):
    task, config = agent_task(tmp_path)
    lint_task(task, config)
    settings = task / "task.toml"
    original = settings.read_text()
    settings.write_text(original.replace("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"))
    with pytest.raises(ValueError, match="verifier.env"):
        lint_task(task, config)
    settings.write_text(original)
    judge = task / "tests/judge.toml"
    judge.write_text(judge.read_text().replace('[judge]', '[judge]\nfiles = ["/logs/verifier/reply.txt"]'))
    with pytest.raises(ValueError, match="reads no files"):
        lint_task(task, config)


def test_a_model_call_cannot_stand_in_for_the_planned_agent_judge(tmp_path):
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "reward.json").write_text('{"reward":1}')
    detail = {"kind": "llm", "judge": {"model": "anthropic/claude-opus-5-5", "reasoning_effort": "high"},
              "criteria": [{"name": "explained", "value": 1, "raw": "yes", "reasoning": "The unit is explained."}]}
    (verifier / "reward-details.json").write_text(json.dumps({"judge": detail}))
    expected = {"program": "claude-code", "model": "anthropic/claude-opus-5-5", "effort": "high"}
    with pytest.raises(JudgeError, match="differs from the planned judge"):
        read_reward(verifier, judge=expected)
    detail.update(kind="agent", judge={**detail["judge"], "agent": "claude-code"})
    (verifier / "reward-details.json").write_text(json.dumps({"judge": detail}))
    assert read_reward(verifier, judge=expected) == ({"reward": 1}, {
        "explained": {"passed": True, "reason": "The unit is explained."}})


def test_file_agent_replay_reuses_answers_until_the_copied_input_changes(tmp_path, monkeypatch):
    import rewardkit.reward
    from rewardkit.models import JudgeResult, Score
    from rewardkit.runner import run as rewardkit_run
    from ethevals.regrade_checks import replay

    tests, source, output = tmp_path / "tests", tmp_path / "source", tmp_path / "current"
    tests.mkdir()
    (source / "saved-verifier").mkdir(parents=True)
    output.mkdir()
    (tests / "judge.toml").write_text('[judge]\njudge = "claude-code"\ncwd = "/judge"\n'
        '[[criterion]]\nname = "explained"\ndescription = "Is the unit explained?"\n'
        '[scoring]\naggregation = "all-pass"\n')
    (tests / "reward.toml").write_text('[[reward]]\nname = "reward"\naggregation = "all-pass"\n')
    calls = []

    async def answer(judge, criteria, weights, *args, **kwargs):
        calls.append(1)
        return JudgeResult(scores=[Score(name="explained", value=1, raw="yes", reasoning="The reply names metre.")],
                           output="{}", warnings=[])

    monkeypatch.setattr(rewardkit.reward, "arun_agent", answer)
    rewardkit_run(tests, output=source / "saved-verifier/reward.json")
    (source / "saved-verifier/judge-inputs.json").write_text('{"reply.txt":"old"}')
    (output / "judge-inputs.json").write_text('{"reply.txt":"old"}')
    item = {"source_row": {"checks_inputs": {}}, "checks_inputs": {}, "judge_required": False}
    item_file = tmp_path / "item.json"
    item_file.write_text(json.dumps(item))
    monkeypatch.setenv("ETHEVALS_REGRADE_ITEM", str(item_file))
    monkeypatch.setenv("ETHEVALS_REGRADE_SOURCE", str(source))
    monkeypatch.setenv("REWARDKIT_LOG_DIR", str(output))
    replay(tests, output=output / "reward.json")
    assert (len(calls), read_reward(output)) == (1, ({"reward": 1.0}, {
        "explained": {"passed": True, "reason": "The reply names metre."}}))
    (output / "judge-inputs.json").write_text('{"reply.txt":"changed"}')
    item["judge_required"] = True
    item_file.write_text(json.dumps(item))
    replay(tests, output=output / "reward.json")
    assert (len(calls), read_reward(output)[0]) == (2, {"reward": 1.0})
