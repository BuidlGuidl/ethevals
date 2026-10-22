import asyncio
import json
from pathlib import Path
import shutil
import os
import subprocess

import pytest

from ethevals.harbor_tasks import lint_task
from ethevals.job_config import load_job
from ethevals.jobs import plan
from test_jobs import job_config, task_folder
from test_vanilla import stand_in


def add_judge(task):
    (task / "tests/judge.toml").write_text('''[judge]
judge = "anthropic/claude-opus-5-5"
atif-trajectory = "/logs/agent/trajectory.json"
guard = "flag"
[scoring]
aggregation = "all-pass"
[[criterion]]
name = "explained"
type = "binary"
description = "Did the reply explain the unit?"
''')
    (task / "tests/reward.toml").write_text(
        '[[reward]]\nname = "reward"\naggregation = "all-pass"\n')
    settings = task / "task.toml"
    settings.write_text(settings.read_text() +
                        '\n[verifier.env]\nANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"\n')


@pytest.mark.parametrize("before,after,message", [
    ('type = "binary"', 'type = "likert"', "binary"),
    ('name = "explained"', 'name = " "', "name"),
    ('guard = "flag"', 'guard = "off"', "guard"),
    ('/logs/agent/trajectory.json', '/app/reply.json', "trajectory"),
    ('aggregation = "all-pass"', 'aggregation = "weighted-mean"', "all-pass"),
])
def test_lint_enforces_judge_rules(tmp_path, before, after, message):
    task = task_folder(tmp_path)
    add_judge(task)
    lint_task(task)
    judge = task / "tests/judge.toml"
    judge.write_text(judge.read_text().replace(before, after))
    with pytest.raises(ValueError, match=message):
        lint_task(task)


def test_lint_requires_all_pass_across_judges_and_tests(tmp_path):
    task = task_folder(tmp_path)
    add_judge(task)
    lint_task(task)
    reward = task / "tests/reward.toml"
    reward.write_text(reward.read_text().replace('aggregation = "all-pass"', 'aggregation = "weighted-mean"'))
    with pytest.raises(ValueError, match="criteria and tests must contribute to all-pass reward"):
        lint_task(task)


@pytest.mark.parametrize("variable", ["CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_API_KEY", "CUSTOM_SECRET"])
def test_only_the_judge_key_can_enter_verifier_env(tmp_path, variable):
    task = task_folder(tmp_path)
    add_judge(task)
    lint_task(task)
    settings = task / "task.toml"
    settings.write_text(settings.read_text() + f'{variable} = "${{{variable}}}"\n')
    with pytest.raises(ValueError, match="verifier.env"):
        lint_task(task)


def test_judge_key_cannot_alias_a_plan_token_or_exist_without_a_judge(tmp_path):
    task = task_folder(tmp_path)
    add_judge(task)
    settings = task / "task.toml"
    original = settings.read_text()
    settings.write_text(original.replace('${ANTHROPIC_API_KEY}', '${CLAUDE_CODE_OAUTH_TOKEN}'))
    with pytest.raises(ValueError, match="verifier.env"):
        lint_task(task)
    settings.write_text(original)
    lint_task(task)
    (task / "tests/judge.toml").unlink()
    with pytest.raises(ValueError, match="verifier.env"):
        lint_task(task)


def test_judge_error_never_schedules_an_agent_retry(tmp_path):
    task = task_folder(tmp_path)
    add_judge(task)
    config = load_job(job_config(tmp_path, "api_key"))
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    assert (item["agent_reserve_usd"], item["judge_reserve_usd"], item["worst_case_usd"]) == (3, 6, 18)
    row = {**item, "status": "error", "error_kind": "judge"}
    report = plan([task], config, [row], n_attempts=1)
    assert (report["missing"], report["exhausted_errors"], report["worst_case_usd"]) == ([], [row], 0)


@pytest.mark.parametrize("error_kind", ["judge", "RewardFileNotFoundError"])
def test_explicit_judge_recovery_selects_one_trial_and_reserves_one_execution(tmp_path, error_kind):
    from support import cli

    task = task_folder(tmp_path)
    add_judge(task)
    config = job_config(tmp_path, "api_key")
    item = plan([task], load_job(config), [], n_attempts=1)["missing"][0]
    from ethevals.trial_rows import SCHEMA_VERSION
    row = {**item, "schema_version": SCHEMA_VERSION, "status": "error", "error_kind": error_kind, "retry": 1}
    rows = tmp_path / "rows.jsonl"
    rows.write_text(json.dumps(row) + "\n")
    args = ["--config", config, "--tasks", task, "--agents", "local", "--modes", "internet",
            "--rows", rows, "--output", tmp_path / "recovery", "--retry-judge-error"]
    unnamed = cli("-m", "ethevals.cli", "plan", *args, "--budget", 9)
    assert unnamed.returncode == 2
    assert "requires --trial" in unnamed.stderr
    admitted = cli("-m", "ethevals.cli", "plan", *args, "--trial", 1, "--budget", 9)
    assert admitted.returncode == 0, admitted.stderr
    report = json.loads(admitted.stdout)
    assert [(item["trial"], item["retry"], item["remaining_executions"], item["worst_case_usd"])
            for item in report["missing"]] == [(1, 2, 1, 9)]
    refused = cli("-m", "ethevals.cli", "run", *args, "--trial", 1, "--budget", 8)
    assert refused.returncode == 2
    assert "Budget exceeded" in refused.stderr
    assert not (tmp_path / "recovery/jobs").exists()
    unbudgeted = cli("-m", "ethevals.cli", "run", *args, "--trial", 1)
    assert unbudgeted.returncode == 2
    assert "requires --budget" in unbudgeted.stderr
    assert json.loads(rows.read_text()) == row
    rows.write_text(json.dumps({**row, "error_kind": "AgentAuthenticationError"}) + "\n")
    other = cli("-m", "ethevals.cli", "plan", *args, "--trial", 1, "--budget", 9)
    assert other.returncode == 0, other.stderr
    other_report = json.loads(other.stdout)
    assert (other_report["missing_trials"], other_report["worst_case_usd"],
            other_report["exhausted_errors"][0]["error_kind"]) == (0, 0, "AgentAuthenticationError")


@pytest.mark.parametrize("mode,reserve", [("batched", 12), ("individual", 24)])
def test_plan_reserves_samples_and_the_individual_guard_call(tmp_path, mode, reserve):
    task = task_folder(tmp_path)
    add_judge(task)
    judge = task / "tests/judge.toml"
    judge.write_text(judge.read_text().replace('[judge]', f'[judge]\nsamples = 2\nmode = "{mode}"'))
    config = load_job(job_config(tmp_path))
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    assert (item["agent_reserve_usd"], item["judge_reserve_usd"], item["worst_case_usd"]) == (0, reserve, reserve * 2)


def test_board_config_overrides_the_task_judge_without_agent_credentials(tmp_path, monkeypatch):
    from harbor.job import Job
    from ethevals.jobs import budget_check, run

    task = task_folder(tmp_path)
    add_judge(task)
    config = load_job(job_config(tmp_path, "free"))
    config.judge.model, config.judge.effort, config.judge.paid_by = "openai/gpt-5", "low", "free"
    captured = []

    class Captured(Exception):
        pass

    async def create(harbor_config):
        captured.append(harbor_config.verifier.env)
        raise Captured

    monkeypatch.setattr(Job, "create", create)
    with pytest.raises(Captured):
        asyncio.run(run(budget_check(plan([task], config, [], n_attempts=1), 0), config, tmp_path / "out", []))
    assert captured == [{"REWARDKIT_JUDGE": "openai/gpt-5", "REWARDKIT_REASONING_EFFORT": "low",
                         "CLAUDE_CODE_OAUTH_TOKEN": "", "REWARDKIT_FORCE_SUBSCRIPTION": ""}]


def test_export_card_explains_the_required_judge_key(tmp_path):
    from ethevals.hf import write_hf

    task = task_folder(tmp_path)
    add_judge(task)
    output = tmp_path / "hf"
    write_hf([task], output)
    card = (output / "README.md").read_text()
    assert "require `ANTHROPIC_API_KEY` through `[verifier.env]`" in card
    assert "A missing key stops Harbor with the variable's name." in card
    assert (output / "tasks/concepts--question/tests/judge.toml").read_bytes() == (task / "tests/judge.toml").read_bytes()


def test_free_check_skips_nested_judges_and_preserves_programmatic_checks(tmp_path, monkeypatch):
    from harbor.job import Job
    from rewardkit.runner import run as run_rewardkit
    from ethevals.harbor_tasks import free_check

    task = task_folder(tmp_path)
    add_judge(task)
    group = task / "tests/judgment"
    group.mkdir()
    (task / "tests/judge.toml").rename(group / "judge.toml")
    (group / "reward.toml").write_text('[[reward]]\naggregation = "all-pass"\nweights = {judge = 1}\n')
    (task / "tests/reward.toml").write_text(
        '[[reward]]\nname = "reward"\naggregation = "all-pass"\nweights = {judgment = 1, output = 1}\n')
    (task / "tests/output.py").write_text('import rewardkit as rk\nrk.file_exists("answer.txt", name="answer")\n')
    before = {file.relative_to(task): file.read_bytes() for file in task.rglob("*") if file.is_file()}

    class SavedJob:
        def __init__(self, config):
            self.config = config

        async def run(self):
            folder = tmp_path / "out" / self.config.job_name / "trial"
            (folder / "verifier").mkdir(parents=True)
            if self.config.job_name == "oracle":
                (folder / "answer.txt").write_text("metre")
            staged = self.config.tasks[0].path
            rewards = await asyncio.to_thread(run_rewardkit, staged / "tests", workspace=folder,
                                             output=folder / "verifier/reward.json")
            (folder / "result.json").write_text(json.dumps({"config": {"task": {"path": str(staged)}},
                "verifier_result": {"rewards": rewards}}))

    async def create(config):
        assert config.verifier.env == {"ANTHROPIC_API_KEY": ""}
        return SavedJob(config)

    monkeypatch.setattr(Job, "create", create)
    lint_task(task)
    asyncio.run(free_check([task], tmp_path / "out"))
    assert {file.relative_to(task): file.read_bytes() for file in task.rglob("*") if file.is_file()} == before
    for agent, expected in (("oracle", 1), ("nop", 0)):
        assert json.loads((tmp_path / "out" / agent / "trial/verifier/reward.json").read_text()) == {"reward": expected}


@pytest.mark.parametrize("confirmed", [True, False])
def test_task_criterion_runs_in_rewardkit_and_reaches_the_row(tmp_path, confirmed):
    from ethevals.trial_rows import results_row

    root = Path(__file__).resolve().parents[2]
    task = next(path.parent.parent for path in (root / "tasks").rglob("tests/transfer.toml"))
    tests = tmp_path / "tests"
    tests.mkdir()
    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    folder = tmp_path / "trial"
    shutil.copytree(fixture, folder)
    trajectory = folder / "agent/trajectory.json"
    saved = json.loads(trajectory.read_text())
    saved["steps"][-1]["message"] = "Confirmed the transaction receipt." if confirmed else "No action taken."
    trajectory.write_text(json.dumps(saved))
    (tests / "transfer.toml").write_text((task / "tests/transfer.toml").read_text().replace(
        "/logs/agent/trajectory.json", str(trajectory)))
    shutil.copy(task / "tests/reward.toml", tests)
    (tests / "reward.toml").write_text('[[reward]]\nname = "reward"\naggregation = "all-pass"\n')
    (tests / "checks.py").write_text(
        'from rewardkit import criterion\n@criterion\ndef state(workspace):\n'
        '    return {"score": 1, "reasoning": "State matches."}\n')

    def reply(request):
        passed = "Confirmed the transaction receipt." in json.dumps(request["messages"])
        return json.dumps({"verified_transfer": {"score": "yes" if passed else "no",
            "reasoning": "Receipt read." if passed else "No receipt read."},
            "guard": {"score": "no", "reasoning": "No judge instructions."}})

    with stand_in(reply=reply) as (completion, requests):
        result = subprocess.run(["rewardkit", str(tests), "--workspace", str(tmp_path),
            "--output", str(folder / "verifier/reward.json"), "--judge", "openai/gpt-5"],
            env={**os.environ, "OPENAI_API_KEY": completion["api_key"],
                 "OPENAI_API_BASE": completion["api_base"], "REWARDKIT_REASONING_EFFORT": "high"},
            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(requests) == 1
    rewards = json.loads((folder / "verifier/reward.json").read_text())
    result_record = json.loads((folder / "result.json").read_text())
    result_record["verifier_result"]["rewards"] = rewards
    (folder / "result.json").write_text(json.dumps(result_record))
    metadata = json.loads((folder / "board.json").read_text())
    metadata.update(judge={"model": "openai/gpt-5", "effort": "high"}, judge_paid_by="free")
    row = results_row(folder, metadata)
    assert (row["status"], row["rewards"]["reward"], row["checks"]["verified_transfer"], row["judge_cost_usd"]) == (
        "passed" if confirmed else "failed", int(confirmed),
        {"passed": confirmed, "reason": "Receipt read." if confirmed else "No receipt read."}, 0)


@pytest.mark.parametrize("error", ["judge timed out after 1s", "The reply is invalid."])
def test_rewardkit_judge_errors_keep_test_checks_and_usage(tmp_path, error):
    from ethevals.trial_rows import results_row

    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    folder = tmp_path / "trial"
    shutil.copytree(fixture, folder)
    details = json.loads((folder / "verifier/reward-details.json").read_text())
    details["judgment"] = {"kind": "llm", "judge": {"model": "openai/gpt-5", "reasoning_effort": "high"},
        "usage": {"cost_usd": 0.0123}, "criteria": [{"name": "explained", "value": 0, "error": error}]}
    (folder / "verifier/reward-details.json").write_text(json.dumps(details))
    metadata = json.loads((folder / "board.json").read_text())
    metadata.update(judge={"model": "openai/gpt-5", "effort": "high"}, judge_paid_by="api_key")
    row = results_row(folder, metadata)
    assert (row["status"], row["error_kind"], row["error_reason"], row["judge_cost_usd"], row["checks"]) == (
        "error", "judge", f"explained: {error}", 0.0123,
        {"unit": {"passed": True, "reason": "The final reply matches."}})


@pytest.mark.parametrize("reply", ["timeout", "bad-json", "bad-binary"])
def test_real_rewardkit_failure_is_a_trial_error_without_agent_retry(tmp_path, monkeypatch, reply):
    import litellm
    from rewardkit.runner import run as run_rewardkit
    from ethevals.trial_rows import results_row

    task = task_folder(tmp_path)
    add_judge(task)
    judge = task / "tests/judge.toml"
    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    folder = tmp_path / "trial"
    shutil.copytree(fixture, folder)
    judge.write_text(judge.read_text().replace('/logs/agent/trajectory.json', str(folder / "agent/trajectory.json")))
    output = folder / "verifier"
    for file in output.iterdir():
        file.unlink()
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs["model"])
        if reply == "timeout":
            raise litellm.Timeout(message="Stand-in timeout.", model="gpt-5", llm_provider="openai")
        content = "unparseable" if reply == "bad-json" else json.dumps({
            "explained": {"score": "maybe", "reasoning": "Uncertain."},
            "guard": {"score": "no", "reasoning": "No judge instructions."}})
        return litellm.ModelResponse(model="gpt-5", choices=[{"message": {"content": content}}],
                                    usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})

    monkeypatch.setattr(litellm, "acompletion", completion)
    monkeypatch.setenv("REWARDKIT_JUDGE", "openai/gpt-5")
    monkeypatch.setenv("REWARDKIT_REASONING_EFFORT", "high")
    if reply == "bad-json":
        with pytest.raises(Exception):
            run_rewardkit(task / "tests", workspace=tmp_path, output=output / "reward.json")
    else:
        run_rewardkit(task / "tests", workspace=tmp_path, output=output / "reward.json")
    assert calls == ["openai/gpt-5"] * (3 if reply == "bad-json" else 1)
    saved = json.loads((folder / "result.json").read_text())
    if reply == "bad-json":
        saved["verifier_result"] = None
        saved["exception_info"] = {"exception_type": "RewardFileNotFoundError",
            "exception_message": "Verifier wrote no reward after a bad judge reply.",
            "exception_traceback": "stand-in", "occurred_at": saved["finished_at"]}
    else:
        saved["verifier_result"]["rewards"] = json.loads((output / "reward.json").read_text())
    (folder / "result.json").write_text(json.dumps(saved))
    metadata = json.loads((folder / "board.json").read_text())
    metadata.update(judge={"model": "openai/gpt-5", "effort": "high"}, judge_paid_by="free")
    row = results_row(folder, metadata)
    assert (row["status"], row["error_kind"]) == (
        "error", "RewardFileNotFoundError" if reply == "bad-json" else "judge")
    assert ("timed out" if reply == "timeout" else "bad judge reply" if reply == "bad-json" else "yes or no") in row["error_reason"]
    judge.write_text(judge.read_text().replace(str(folder / "agent/trajectory.json"), '/logs/agent/trajectory.json'))
    config = load_job(job_config(tmp_path, "free"))
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    report = plan([task], config, [{**item, "status": row["status"], "error_kind": row["error_kind"]}], n_attempts=1)
    assert (report["missing_trials"], len(report["exhausted_errors"]), report["worst_case_usd"]) == (0, 1, 0)


@pytest.mark.docker
def test_claude_plan_token_does_not_reach_a_shared_verifier(tmp_path, monkeypatch):
    import shlex
    from harbor.agents.installed.claude_code import ClaudeCode
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    root = Path(__file__).resolve().parents[2]
    source = next(path.parent.parent for path in (root / "tasks").rglob("tests/transfer.toml"))
    task = tmp_path / source.parent.name / "credential-proof"
    shutil.copytree(source, task)
    (task / "tests/transfer.toml").unlink()
    (task / "tests/reward.toml").write_text('[[reward]]\nname = "reward"\naggregation = "all-pass"\n')
    verifier_probe = '''import json, os, subprocess
from pathlib import Path
from rewardkit.judges import _anthropic_subscription_key
proof = {"plan": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"),
         "api_matches": os.environ.get("ANTHROPIC_API_KEY") == "offline-judge-key",
         "chain_matches_context": int(subprocess.check_output(
             ["cast", "chain-id", "--rpc-url", "http://chain:8545"], text=True)) ==
             json.loads(Path("/workspace/chain_context.json").read_text())["chainId"]}
os.environ.pop("ANTHROPIC_API_KEY", None)
proof["fallback_without_api"] = _anthropic_subscription_key("anthropic/claude-opus-5-5")
os.environ["REWARDKIT_FORCE_SUBSCRIPTION"] = "1"
proof["forced_fallback"] = _anthropic_subscription_key("anthropic/claude-opus-5-5")
Path("/logs/verifier/auth-proof.json").write_text(json.dumps(proof))
'''
    (task / "tests/probe.py").write_text(verifier_probe)
    (task / "tests/test.sh").write_text('#!/bin/sh\nset -eu\npython3 /tests/probe.py\nrewardkit /tests\n')
    (task / "tests/check.py").write_text(
        'from rewardkit import criterion\n@criterion\ndef isolated_credentials(workspace):\n'
        '    return {"score": True, "reasoning": "Verifier probe finished."}\n')
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-offline-ticket-19")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-judge-key")
    monkeypatch.setenv("REWARDKIT_FORCE_SUBSCRIPTION", "1")

    async def setup(self, environment):
        pass

    async def exec_stand_in(self, environment, *, env=None, **kwargs):
        script = '''import json, os
from pathlib import Path
Path('/logs/agent/auth-proof.json').write_text(json.dumps({
    'plan_matches': os.environ.get('CLAUDE_CODE_OAUTH_TOKEN') == 'sk-ant-oat-offline-ticket-19',
    'api': os.environ.get('ANTHROPIC_API_KEY'),
    'container_plan': b'CLAUDE_CODE_OAUTH_TOKEN=' in Path('/proc/1/environ').read_bytes()}))
'''
        return await environment.exec(command="python3 -c " + shlex.quote(script), env=env, user="agent")

    monkeypatch.setattr(ClaudeCode, "setup", setup)
    monkeypatch.setattr(ClaudeCode, "exec_as_agent", exec_stand_in)

    async def trial():
        config = JobConfig(job_name="auth", jobs_dir=tmp_path, quiet=True, n_concurrent_trials=1,
            tasks=[{"path": task}], agents=[{"name": "claude-code", "model_name": "anthropic/claude-opus-5-5",
                "kwargs": {"version": "2.1.284"}, "env": {"CLAUDE_FORCE_OAUTH": "YES"}}],
            environment={"type": "docker"})
        job = await Job.create(config)
        await job.run()

    asyncio.run(trial())
    result_path = next((tmp_path / "auth").glob("*/result.json"))
    result = json.loads(result_path.read_text())
    assert result["exception_info"] is None, result
    assert result["verifier_environment_mode"] == "shared"
    assert json.loads((result_path.parent / "agent/auth-proof.json").read_text()) == {
        "plan_matches": True, "api": None, "container_plan": False}
    assert json.loads((result_path.parent / "verifier/auth-proof.json").read_text()) == {
        "plan": None, "api_matches": True,
        "chain_matches_context": True, "fallback_without_api": None, "forced_fallback": None}


def reach_host(task: Path) -> None:
    """Map host.docker.internal to the host, which Docker on Linux doesn't do by itself."""
    import yaml

    compose = task / "environment/docker-compose.yaml"
    data = yaml.safe_load(compose.read_text()) if compose.exists() else {"services": {}}
    data["services"].setdefault("main", {}).setdefault("extra_hosts", []).append("host.docker.internal:host-gateway")
    compose.write_text(yaml.safe_dump(data, sort_keys=False))


@pytest.mark.docker
def test_plain_harbor_and_board_agree_on_a_saved_judged_chain_trial(tmp_path, monkeypatch):
    from ethevals.trial_rows import results_row

    root = Path(__file__).resolve().parents[2]
    source = next(path.parent.parent for path in (root / "tasks").rglob("tests/transfer.toml"))
    task = tmp_path / source.parent.name / "judged-chain"
    shutil.copytree(source, task)
    reach_host(task)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-judge-key")

    def reply(request):
        confirmed = "balanceOf(address)(uint256)" in json.dumps(request["messages"])
        return json.dumps({"verified_transfer": {"score": "yes" if confirmed else "no",
            "reasoning": "Recipient balance read." if confirmed else "No confirmation read."},
            "guard": {"score": "no", "reasoning": "No judge instructions."}})

    with stand_in(reply=reply, host="0.0.0.0") as (completion, requests):
        env = {"REWARDKIT_JUDGE": "openai/gpt-5", "REWARDKIT_REASONING_EFFORT": "high",
               "OPENAI_API_KEY": completion["api_key"],
               "OPENAI_API_BASE": completion["api_base"].replace("127.0.0.1", "host.docker.internal")}

        for agent, expected in (("oracle", 1), ("nop", 0)):
            # Nop has no trajectory. Supply an empty ATIF reply through the verifier for this stand-in proof.
            if agent == "nop":
                test_script = task / "tests/test.sh"
                test_script.write_text(test_script.read_text().replace("set -eu", "set -eu\n"
                    "printf '%s' '{\"steps\":[{\"source\":\"agent\",\"message\":\"No action taken.\"}]}' > /logs/agent/trajectory.json"))
            command = ["harbor", "run", "-p", str(task), "--agent", agent, "--jobs-dir", str(tmp_path),
                       "--job-name", agent, "--n-concurrent", "1", "--quiet", "--yes"]
            for key, value in env.items():
                command.extend(["--verifier-env", f"{key}={value}"])
            completed = subprocess.run(command, capture_output=True, text=True, timeout=900)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            result_path = next((tmp_path / agent).glob("*/result.json"))
            result = json.loads(result_path.read_text())
            assert result["exception_info"] is None, result
            assert result["verifier_result"]["rewards"]["reward"] == expected
            from ethevals.jobs import task_entry
            metadata = {"task_id": "transactions/judged-chain", "task_hash": task_entry(task)["hash"], "skills_hash": None,
                "agent": agent, "model": "local/model", "effort": None, "mode": "internet", "trial": 1,
                "retry": 0, "paid_by": "free", "agent_version": result["agent_info"]["version"],
                "harbor_version": "0.24.0",
                "judge": {"model": "openai/gpt-5", "effort": "high"}, "judge_paid_by": "free"}
            row = results_row(result_path.parent, metadata)
            assert (row["status"], row["rewards"]["reward"], row["checks"]["verified_transfer"]) == (
                "passed" if expected else "failed", expected, {"passed": bool(expected),
                "reason": "Recipient balance read." if expected else "No confirmation read."})
            (result_path.parent / "board-row.json").write_text(json.dumps(row, indent=2) + "\n")
        assert len(requests) == 2
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    missing = subprocess.run(["harbor", "run", "-p", str(task), "--agent", "nop", "--jobs-dir", str(tmp_path),
        "--job-name", "missing-key", "--n-concurrent", "1", "--quiet", "--yes"], capture_output=True, text=True, timeout=900)
    evidence = missing.stdout + missing.stderr
    for result_path in (tmp_path / "missing-key").glob("*/result.json"):
        result = json.loads(result_path.read_text())
        assert result["exception_info"] is not None
        evidence += result["exception_info"]["exception_message"]
    assert "ANTHROPIC_API_KEY" in evidence


@pytest.mark.docker
def test_harbor_regrade_reuses_artifacts_without_an_agent_run(tmp_path, monkeypatch):
    task = tmp_path / "concepts/question"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/concepts/question", task)
    add_judge(task)
    reach_host(task)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-judge-key")
    passed = False

    def reply(request):
        assert "metre" in json.dumps(request["messages"])
        return json.dumps({"explained": {"score": "yes" if passed else "no", "reasoning": "Stand-in verdict."},
                           "guard": {"score": "no", "reasoning": "No judge instructions."}})

    with stand_in(reply=reply, host="0.0.0.0") as (completion, requests):
        env = {"REWARDKIT_JUDGE": "openai/gpt-5", "OPENAI_API_KEY": completion["api_key"],
               "OPENAI_API_BASE": completion["api_base"].replace("127.0.0.1", "host.docker.internal")}
        flags = [argument for key, value in env.items() for argument in ("--verifier-env", f"{key}={value}")]
        original = subprocess.run(["harbor", "run", "-p", str(task), "--agent", "oracle",
            "--jobs-dir", str(tmp_path), "--job-name", "original", "--n-concurrent", "1", "--quiet", "--yes", *flags],
            capture_output=True, text=True, timeout=900)
        assert original.returncode == 0, original.stdout + original.stderr
        source = next((tmp_path / "original").glob("*/result.json")).parent
        saved = (source / "result.json").read_bytes()
        trajectory = (source / "agent/trajectory.json").read_bytes()
        assert json.loads(saved)["verifier_result"]["rewards"]["reward"] == 0
        passed = True
        regrade = subprocess.run(["harbor", "trial", "regrade", str(source), "-p", str(task),
            "--trials-dir", str(tmp_path), "--trial-name", "regraded", "--yes", *flags],
            capture_output=True, text=True, timeout=900)
        assert regrade.returncode == 0, regrade.stdout + regrade.stderr
        result = json.loads((tmp_path / "regraded/result.json").read_text())
        assert result["exception_info"] is None, result
        assert result["verifier_result"]["rewards"]["reward"] == 1
        assert (source / "result.json").read_bytes() == saved
        assert (tmp_path / "regraded/agent/trajectory.json").read_bytes() == trajectory
        assert len(requests) == 2
