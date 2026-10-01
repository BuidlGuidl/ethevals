from ethevals.actors import select_actors
from ethevals.config import Config
from inspect_ai.agent import AgentState
from inspect_ai.agent._bridge.responses_impl import inspect_responses_api_request_impl
from inspect_ai.agent._bridge.types import AgentBridge
from inspect_ai.model import ChatMessageUser, ModelOutput
import asyncio
import pytest

from support import catalog_quiz, fixture_config


def test_codex_home_is_outside_the_workspace(monkeypatch):
    from ethevals import agents

    observed = {}
    original = agents.codex_cli

    def construct(**settings):
        observed.update(settings)
        return original(**settings)

    monkeypatch.setattr(agents, "codex_cli", construct)
    agents.codex("gpt-5.5", native_search=False, search_limit=8)
    assert (observed["cwd"], observed.get("home_dir")) == ("/workspace", "/home/agent/.codex")


@pytest.mark.parametrize("mode,key", [("vanilla", "opus-5.5"), ("internet", "claude-code-opus-5.5")])
@pytest.mark.parametrize("effort", [None, "medium"])
def test_optional_effort_reaches_model_call(monkeypatch, mode, key, effort):
    data = fixture_config().model_dump()
    del data["models"]["opus-5.5"]["effort"]
    config = Config.model_validate(data)
    if effort:
        config.models["opus-5.5"].effort = effort
    actors_for, _ = select_actors(config, modes=[mode], **{"models" if mode == "vanilla" else "agents": [key]})
    actor = actors_for(catalog_quiz()[1])[0][1]
    observed = []

    def reply(messages, tools, tool_choice, config):
        observed.append(config.reasoning_effort)
        return ModelOutput.from_content("mockllm/opus-5.5", "8004")

    monkeypatch.setattr(actor.model.api, "outputs", reply)
    output = asyncio.run(actor.model.generate([ChatMessageUser(content="Name the ERC.")]))
    assert (output.completion, observed, actor.metadata["effort"]) == ("8004", [effort], effort)


def test_codex_agent_serializes_custom_calls_through_bridge(tmp_path, monkeypatch):
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import solver
    config = fixture_config()
    config.models["gpt-5.5"].model = "mockllm/model"
    actors_for, _ = select_actors(config, agents=["codex-cli-gpt-5.5"], modes=["internet"])
    actor = actors_for(catalog_quiz()[1])[0][1]
    monkeypatch.setattr(actor.model.source.api, "outputs", lambda *args: ModelOutput.for_tool_call(
        "mockllm/model", "exec", {"input": "text(42);"}))
    calls = []

    @solver
    def through_bridge():
        async def solve(state, generate):
            bridge = AgentBridge(AgentState(messages=[]), model="inspect")
            response = await inspect_responses_api_request_impl({
                "model": "gpt-5.5", "input": [{"role": "user", "content": "Run code"}],
                "tools": [{"type": "namespace", "name": "functions", "description": "Tools", "tools": [
                    {"type": "custom", "name": "exec", "description": "Run JavaScript", "format": {"type": "text"}},
                ]}],
            }, None, None, None, bridge)
            call = response.output[-1]
            calls.append((call.type, call.input if call.type == "custom_tool_call" else call.arguments))
            return state
        return solve

    log = eval(Task(dataset=[Sample(input="Run code")], solver=through_bridge(), model=actor.model),
               log_dir=str(tmp_path / "logs"), display="none")[0]
    assert (log.status, calls) == ("success", [("custom_tool_call", "text(42);")])
