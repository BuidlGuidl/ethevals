"""Exercise pinned Harbor auth against a stand-in container, without a CLI call."""
import asyncio
import json
from pathlib import Path

import pytest

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.codex import Codex
from harbor.models.agent.context import AgentContext
from harbor.environments.base import ExecResult
from harbor.agents.factory import AgentFactory
from harbor.job import Job

from ethevals.job_config import check_credentials, load_job
from ethevals.jobs import budget_check, plan, run
from test_jobs import task_folder


class Captured(Exception):
    pass


@pytest.mark.parametrize("key,default_auth,paid_by", [
    ("claude-code-opus-5.5", False, "plan"), ("claude-code-opus-5.5", False, "api_key"),
    ("codex-gpt-6.1-sol", False, "plan"), ("codex-gpt-6.1-sol", True, "plan"),
])
def test_job_config_selects_plan_and_budget_without_shell_force_flags(tmp_path, monkeypatch, key, default_auth, paid_by):
    config, task = load_job(), task_folder(tmp_path)
    monkeypatch.delenv("CLAUDE_FORCE_OAUTH", raising=False)
    monkeypatch.delenv("CODEX_FORCE_AUTH_JSON", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-api-key")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-api-key")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "offline-plan-token")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    auth = tmp_path / ".codex/auth.json"
    auth.parent.mkdir()
    auth.write_text('{"auth_mode":"chatgpt","tokens":{"access_token":"offline-plan-token"}}')
    if default_auth:
        monkeypatch.delenv("CODEX_AUTH_JSON_PATH", raising=False)
    else:
        monkeypatch.setenv("CODEX_AUTH_JSON_PATH", str(auth))
    captured = []

    async def capture(job_config):
        agent_config = job_config.agents[0]
        agent = AgentFactory.create_agent_from_config(agent_config, logs_dir=tmp_path / "agent")
        if key == "claude-code-opus-5.5":
            captured.append((agent_config.env, agent._resolve_auth_env(), agent.options.max_budget_usd,
                             agent.build_cli_flags()))
        else:
            captured.append((agent_config.env, agent._resolve_auth_json_path()))
        raise Captured

    monkeypatch.setattr(Job, "create", capture)
    # Entry keys carry no semantics; retain the shipped entry under another key.
    config.agents = {"selected": config.agents[key]}
    config.agents["selected"].cost_limit_usd = 7.25
    config.agents["selected"].paid_by = paid_by
    if paid_by == "api_key":
        config.agents["selected"].env = {}
        config.agents["selected"].required_env = []
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    report = budget_check(plan([task], config, [], modes=["internet"], n_attempts=1), 20, required=True)
    with pytest.raises(Captured):
        asyncio.run(run(report, config, tmp_path / "out", []))
    if key == "claude-code-opus-5.5":
        env, credentials, budget, flags = captured[0]
        if paid_by == "api_key":
            assert env == {}
            assert credentials == {"ANTHROPIC_API_KEY": "offline-api-key"}
            assert budget == "7.25"
            assert "--max-budget-usd 7.25" in flags
        else:
            assert env == {"CLAUDE_FORCE_OAUTH": "YES"}
            assert credentials == {"CLAUDE_CODE_OAUTH_TOKEN": "offline-plan-token"}
            assert budget is None
            assert "--max-budget-usd" not in flags
    else:
        assert captured == [({"CODEX_FORCE_AUTH_JSON": "YES", "CODEX_AUTH_JSON": ""}, auth)]


@pytest.mark.parametrize("key,empty", [
    ("claude-code-opus-5.5", False), ("claude-code-opus-5.5", True),
    ("codex-gpt-6.1-sol", False), ("codex-gpt-6.1-sol", True),
])
def test_missing_plan_credential_refuses_before_harbor(tmp_path, monkeypatch, key, empty):
    config, task = load_job(), task_folder(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("CODEX_AUTH_JSON_PATH", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-api-key")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-api-key")
    if empty:
        variable = "CLAUDE_CODE_OAUTH_TOKEN" if key == "claude-code-opus-5.5" else "CODEX_AUTH_JSON_PATH"
        monkeypatch.setenv(variable, "")

    async def refuse(*args, **kwargs):
        raise AssertionError("Harbor cannot start without the plan credential.")

    monkeypatch.setattr(Job, "create", refuse)
    config.agents = {"selected": config.agents[key]}
    report = budget_check(plan([task], config, [], modes=["internet"], n_attempts=1), 0, required=True)
    with pytest.raises(ValueError, match="selected: missing"):
        asyncio.run(run(report, config, tmp_path / "out", []))
    assert not (tmp_path / "out/jobs").exists()


def test_claude_plan_uses_its_token_and_board_judge_requires_an_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "offline-plan-token")
    monkeypatch.setenv("CLAUDE_FORCE_OAUTH", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-judge-key")
    requests = []

    class Container:
        default_user = None

        async def exec(self, **kwargs):
            requests.append(kwargs)
            raise Captured

    agent = ClaudeCode(logs_dir=tmp_path, model_name="anthropic/claude-opus-5-5")
    with pytest.raises(Captured):
        asyncio.run(agent.run("Name a unit.", Container(), AgentContext()))
    assert requests[0]["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "offline-plan-token"
    assert "ANTHROPIC_API_KEY" not in requests[0]["env"]
    from ethevals.job_config import JudgeSettings, check_judge_key
    check_judge_key(JudgeSettings())
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "offline-judge-key"


@pytest.mark.parametrize("auth_mode,api_key,accepted", [
    ("chatgpt", None, True), ("chatgpt", "offline-exchanged-key", True),
    ("apikey", "offline-api-key", False), ("apikey", None, False), (None, None, False),
])
def test_codex_uploads_chatgpt_auth_file_instead_of_an_api_key(tmp_path, monkeypatch, auth_mode, api_key, accepted):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"auth_mode": auth_mode, "OPENAI_API_KEY": api_key, "tokens": {
        "access_token": "offline-plan-token", "account_id": "offline-account",
        "id_token": "offline-id-token", "refresh_token": "offline-refresh-token"}}))
    monkeypatch.setenv("CODEX_AUTH_JSON_PATH", str(auth))
    monkeypatch.setenv("CODEX_FORCE_AUTH_JSON", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-vanilla-key")
    requests, uploads = [], []

    class Container:
        default_user = None

        async def exec(self, **kwargs):
            requests.append(kwargs)
            return ExecResult(return_code=0, stdout="", stderr="")

        async def upload_file(self, source, target):
            uploads.append((Path(source).read_text(), target))
            raise Captured

    agent = Codex(logs_dir=tmp_path, model_name="openai/gpt-6.1-sol")
    settings = load_job().agents["codex-gpt-6.1-sol"]
    if not accepted:
        with pytest.raises(ValueError, match="plan tokens"):
            check_credentials(settings, "selected")
        return
    check_credentials(settings, "selected")
    with pytest.raises(Captured):
        asyncio.run(agent.run("Name a unit.", Container(), AgentContext()))
    assert uploads == [(auth.read_text(), "/tmp/codex-secrets/auth.json")]
    assert requests[0]["env"] == {"CODEX_HOME": "/tmp/codex-home"}


@pytest.mark.parametrize("through_ci", [False, True, "json"])
def test_api_key_only_auth_file_is_refused_for_a_codex_plan(tmp_path, monkeypatch, through_ci):
    import argparse
    from test_ci import ci

    config, task = load_job(), task_folder(tmp_path)
    config.agents = {"selected": config.agents["codex-gpt-6.1-sol"]}
    auth = tmp_path / "auth.json"
    auth.write_text('{"OPENAI_API_KEY":"offline-key-only"}')
    monkeypatch.setenv("CODEX_AUTH_JSON_PATH", str(auth))
    monkeypatch.delenv("CODEX_AUTH_JSON", raising=False)
    if through_ci == "json":
        monkeypatch.setenv("CODEX_AUTH_JSON", auth.read_text())
    item = plan([task], config, [], modes=["internet"], n_attempts=1)["missing"][0]
    assert (item["paid_by"], item["worst_case_usd"]) == ("plan", 0)

    async def refuse(*args, **kwargs):
        raise AssertionError("An API key cannot start a plan-funded trial.")

    monkeypatch.setattr(Job, "create", refuse)
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="plan tokens"):
        if through_ci:
            saved = tmp_path / "plan"
            saved.mkdir()
            (saved / "trials.json").write_text(json.dumps([{
                "missing": [item], "selected": [], "worst_case_usd": 0}]))
            (saved / "config.json").write_text(config.model_dump_json())
            ci.run_trial(argparse.Namespace(plan=saved, index=0, output=output))
        else:
            asyncio.run(run(budget_check(plan([task], config, [], modes=["internet"], n_attempts=1), 0),
                            config, output, []))
    assert not (output / "jobs").exists()


@pytest.mark.parametrize("agent_has_plan", [False, True])
@pytest.mark.parametrize("templated", [False, True])
def test_plan_checks_the_auth_file_harbor_uploads(tmp_path, monkeypatch, agent_has_plan, templated):
    config, task = load_job(), task_folder(tmp_path)
    config.agents = {"selected": config.agents["codex-gpt-6.1-sol"]}
    plan_auth, key_auth = tmp_path / "plan.json", tmp_path / "key.json"
    plan_auth.write_text('{"auth_mode":"chatgpt","tokens":{"access_token":"offline-plan-token"}}')
    key_auth.write_text('{"auth_mode":"apikey","OPENAI_API_KEY":"offline-key-only"}')
    selected = plan_auth if agent_has_plan else key_auth
    monkeypatch.setenv("CODEX_AUTH_JSON_PATH", str(key_auth if agent_has_plan else plan_auth))
    monkeypatch.setenv("SELECTED_AUTH_PATH", str(selected))
    config.agents["selected"].env["CODEX_AUTH_JSON_PATH"] = "${SELECTED_AUTH_PATH}" if templated else str(selected)
    uploads = []

    class Container:
        default_user = None

        async def exec(self, **kwargs):
            return ExecResult(return_code=0, stdout="", stderr="")

        async def upload_file(self, source, target):
            uploads.append((Path(source).read_text(), target))
            raise Captured

    async def capture(job_config):
        agent = AgentFactory.create_agent_from_config(job_config.agents[0], logs_dir=tmp_path / "agent")
        await agent.run("Name a unit.", Container(), AgentContext())

    monkeypatch.setattr(Job, "create", capture)
    report = budget_check(plan([task], config, [], modes=["internet"], n_attempts=1), 0)
    assert report["worst_case_usd"] == 0
    with pytest.raises(Captured if agent_has_plan else ValueError, match=None if agent_has_plan else "plan tokens"):
        asyncio.run(run(report, config, tmp_path / "out", []))
    if agent_has_plan:
        assert uploads == [(plan_auth.read_text(), "/tmp/codex-secrets/auth.json")]
    else:
        assert not (tmp_path / "out/jobs").exists()


@pytest.mark.parametrize("field", ["missing_credential", "agent_budget", "model_budget"])
def test_job_load_rejects_missing_plan_credentials_and_duplicate_budget_settings(tmp_path, field):
    from test_jobs import job_config

    path = job_config(tmp_path, "api_key")
    data = json.loads(path.read_text())
    if field == "missing_credential":
        data["agents"]["local"]["paid_by"] = "plan"
        message = "plan.*credential requirement"
    else:
        owner = data["agents"]["local"] if field == "agent_budget" else data["models"]["local"]
        owner["kwargs"] = {"max_budget_usd": "999"}
        message = "cost_limit_usd"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=message):
        load_job(path)
