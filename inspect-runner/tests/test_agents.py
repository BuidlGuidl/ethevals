import asyncio
import json

import pytest
from pydantic import ValidationError
from inspect_ai.model import ChatMessageUser, GenerateConfig, ModelOutput, get_model
from inspect_ai.tool import ToolInfo

from ethevals import agents
from ethevals.actors import player
from ethevals.config import Config, load_config


@pytest.mark.parametrize("key,harness", [
    ("opus", "claude_code"), ("codex", "codex_cli"),
    ("kimi", "opencode"), ("glm", "opencode"),
])
def test_agent_settings(monkeypatch, key, harness):
    config = load_config()
    config.search_provider = "https://example.org/search"
    config.models[key].effort = "medium"
    monkeypatch.setattr(agents, harness, lambda **kwargs: kwargs)
    monkeypatch.setattr(agents, "as_solver", lambda agent: agent)
    settings = agents.AGENTS[harness].factory(config, config.models[key])
    assert settings["cwd"] == "/workspace"
    assert [server.model_dump(exclude_none=True) for server in settings["mcp_servers"]] == [
        {"type": "http", "name": "exa", "tools": "all", "url": "https://example.org/search"},
    ]
    assert settings["version"] == agents.AGENTS[harness].version
    if harness == "claude_code":
        assert settings["effort"] == "medium"
        assert settings["disallowed_tools"] == ["WebSearch"]
        assert settings["retry_uncaught_errors"] == 0
    elif harness == "codex_cli":
        assert settings["config_overrides"] == {"model_reasoning_effort": '"medium"'}
        assert settings["web_search"] == "disabled"
        assert settings["model_config"] == "gpt-6-sol"
    else:
        assert json.loads(settings["env"]["OPENCODE_CONFIG_CONTENT"]) == {"tools": {"websearch": False}}
        assert settings["opencode_model"] == "anthropic/claude-sonnet-4-5"
    config.search_provider = None
    assert agents.AGENTS[harness].factory(config, config.models[key])["mcp_servers"] == []


@pytest.mark.parametrize("key,model,harness", [
    ("codex", "openrouter/openai/gpt-6-sol", "codex_cli"),
    ("kimi", "openrouter/moonshotai/kimi-k3", "opencode"),
    ("glm", "openrouter/z-ai/glm-5.3", "opencode"),
])
def test_player_selects_model_and_effort(key, model, harness):
    config = load_config()
    assert config.models[key].model == model
    config.models[key].model = "mockllm/model"
    config.models[key].effort = "low"
    actor = player(config, key, "internet")
    assert str(actor.model) == "mockllm/model"
    assert actor.model.config.reasoning_effort == "low"
    assert actor.metadata["harness"] == harness
    assert actor.metadata["effort"] == "low"


def test_unknown_harness_fails_config_validation():
    data = load_config().model_dump()
    data["models"]["codex"]["harness"] = "missing"
    with pytest.raises(ValidationError, match="models.codex.harness: unknown harness 'missing'"):
        Config.model_validate(data)


def test_codex_restores_custom_tool_calls_from_json_replies():
    reply = ModelOutput.for_tool_call("mockllm/model", "exec", {"input": "text(42);"})
    reply.choices[0].message.tool_calls += ModelOutput.for_tool_call(
        "mockllm/model", "wait", {"cell_id": "cell-1"},
    ).choices[0].message.tool_calls
    model = get_model("mockllm/model", custom_outputs=[reply])
    output = asyncio.run(agents.codex_tool_types(
        model, [ChatMessageUser(content="Run the tools.")],
        [ToolInfo(name="exec", description="Run JavaScript", options={"custom_format": {"type": "text"}}),
         ToolInfo(name="wait", description="Wait for execution")],
        "auto", GenerateConfig(),
    ))
    assert [(call.function, call.type, call.arguments) for call in output.choices[0].message.tool_calls] == [
        ("exec", "custom", {"input": "text(42);"}),
        ("wait", "function", {"cell_id": "cell-1"}),
    ]
