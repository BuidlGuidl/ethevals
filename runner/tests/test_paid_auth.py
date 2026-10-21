"""Exercise pinned Harbor auth against a stand-in container, without a CLI call."""
import asyncio
import json
from pathlib import Path

import pytest

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.codex import Codex
from harbor.models.agent.context import AgentContext
from harbor.environments.base import ExecResult


class Captured(Exception):
    pass


def test_claude_plan_token_reaches_container_while_judge_key_stays_on_host(tmp_path, monkeypatch):
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
    from ethevals.judge import JudgeSettings, check_judge_key
    check_judge_key(JudgeSettings())
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "offline-judge-key"


def test_codex_uploads_chatgpt_auth_file_instead_of_an_api_key(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"access_token": "offline-plan-token"}}))
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

    agent = Codex(logs_dir=tmp_path, model_name="openai/gpt-6")
    with pytest.raises(Captured):
        asyncio.run(agent.run("Name a unit.", Container(), AgentContext()))
    assert uploads == [(auth.read_text(), "/tmp/codex-secrets/auth.json")]
    assert requests[0]["env"] == {"CODEX_HOME": "/tmp/codex-home"}
