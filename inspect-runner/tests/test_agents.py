import json

from ethevals import agents
from ethevals.actors import select_actors
from ethevals.config import Config
from ethevals.images.tag import image_tag
from inspect_ai.agent import AgentState
from inspect_ai.agent._bridge.responses_impl import inspect_responses_api_request_impl, responses_output_items_from_assistant_message, tools_from_responses_tool
from inspect_ai.agent._bridge.types import AgentBridge
from inspect_ai.agent._bridge.util import bridge_generate, in_bridge_model_generate
from inspect_ai.model import ChatMessageUser, ContentToolUse, GenerateConfig, ModelOutput, get_model
from inspect_ai.model._openai import chat_tool_calls_from_openai
from inspect_ai.tool import ToolInfo
from inspect_swe._codex_cli._events.consumer import CodexConsumer
from openai.types.chat import ChatCompletionMessage
from pydantic import ValidationError
import asyncio
import inspect
import pytest

from support import catalog_quiz, fixture_config



@pytest.mark.parametrize("key,harness", [
    ("claude-code-opus-5.5", "claude_code"), ("codex-cli-gpt-5.5", "codex_cli"),
    ("opencode-kimi-k3", "opencode"), ("opencode-glm-5.3", "opencode"),
])
def test_registry_builds_solver(key, harness):
    config = fixture_config()
    for search in [True, False]:
        config.search = search
        solve = agents.HARNESSES[harness].build(config, config.agents[key].cli_model, config.agents[key].search)
        assert inspect.iscoroutinefunction(solve)
        assert list(inspect.signature(solve).parameters) == ["state", "generate"]


@pytest.mark.parametrize("key,harness", [
    ("codex-cli-gpt-5.5", "codex_cli"),
    ("opencode-kimi-k3", "opencode"),
    ("opencode-glm-5.3", "opencode"),
])
def test_agent_selects_model_and_effort(key, harness):
    config = fixture_config()
    config.models[config.agents[key].model].model = "mockllm/model"
    config.models[config.agents[key].model].effort = "low"
    actors_for, _ = select_actors(config, agents=[key], modes=["internet"])
    actor = actors_for(catalog_quiz()[1])[0][1]
    assert str(actor.model) == "mockllm/model"
    assert actor.model.config.reasoning_effort == "low"
    assert actor.metadata["harness"] == harness
    assert actor.metadata["effort"] == "low"


def test_unknown_harness_fails_config_validation():
    data = fixture_config().model_dump()
    data["agents"]["codex-cli-gpt-5.5"]["harness"] = "missing"
    with pytest.raises(ValidationError, match="agents.codex-cli-gpt-5.5.harness: unknown harness 'missing'"):
        Config.model_validate(data)


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


@pytest.mark.parametrize("arguments,expected_type,expected", [
    ('{"input":"text(42);"}', "custom_tool_call", "text(42);"),
    ('{}', "function_call", {}),
    ('{"input":', "function_call", {}),
    ('{"code":"a","input":"b"}', "function_call", {"code": "a", "input": "b"}),
    ('{"input":7}', "function_call", {"input": 7}),
])
def test_codex_parser_to_serializer(arguments, expected_type, expected):
    tools = tools_from_responses_tool({
        "type": "namespace", "name": "functions", "description": "Tools", "tools": [
            {"type": "custom", "name": "exec", "description": "Run JavaScript", "format": {"type": "text"}},
        ],
    }, None, None, True)
    message = ChatCompletionMessage(role="assistant", tool_calls=[{
        "id": "call_1", "type": "function", "function": {"name": "exec", "arguments": arguments},
    }])
    reply = ModelOutput.for_tool_call("mockllm/model", "exec", {})
    reply.message.tool_calls = chat_tool_calls_from_openai(message, tools)
    model = agents.CodexModel(get_model("mockllm/model", custom_outputs=[reply], memoize=False))
    output = asyncio.run(model.generate([ChatMessageUser(content="Run code")], tools=tools))
    call = responses_output_items_from_assistant_message(output.message)[-1]
    assert call.type == expected_type
    assert (call.input if call.type == "custom_tool_call" else json.loads(call.arguments)) == expected
    assert bool(output.message.tool_calls[0].parse_error) == (arguments == '{"input":')


@pytest.mark.parametrize("options", [None, {
    "custom_format": {"type": "text"}, "__responses_namespace__": ("other", "Other tools"),
}])
def test_codex_keeps_bridge_events_and_ordinary_functions(options):
    events = []
    markers = []

    class Sink(CodexConsumer):
        def on_pending(self, event):
            events.append("pending")
            super().on_pending(event)

        def on_complete(self, event):
            events.append("complete")
            super().on_complete(event)

    def reply(*args):
        markers.append(in_bridge_model_generate())
        return ModelOutput.for_tool_call("mockllm/model", "exec", {"input": "ordinary"})

    model = agents.CodexModel(get_model("mockllm/model", custom_outputs=reply, memoize=False))
    messages = [ChatMessageUser(content="Run code")]
    bridge = AgentBridge(AgentState(messages=messages), model_event_sink=Sink())
    output, _ = asyncio.run(bridge_generate(
        bridge, model, messages, [ToolInfo(name="exec", description="An ordinary function", options=options)], "auto", GenerateConfig(),
    ))
    assert events == ["pending", "complete"]
    assert markers == [True]
    assert output.message.tool_calls[0].type == "function"
    assert output.message.tool_calls[0].arguments == {"input": "ordinary"}


def test_inspect_still_needs_custom_call_adapter():
    """Delete our adapter when Inspect restores the declared custom type itself."""
    model = get_model("mockllm/model", custom_outputs=[
        ModelOutput.for_tool_call("mockllm/model", "exec", {"input": "text(42);"}),
    ], memoize=False)
    bridge = AgentBridge(AgentState(messages=[]), model_aliases={"inspect": model})
    response = asyncio.run(inspect_responses_api_request_impl({
        "model": "inspect", "input": [{"role": "user", "content": "Run code"}],
        "tools": [{"type": "namespace", "name": "functions", "description": "Tools", "tools": [
            {"type": "custom", "name": "exec", "description": "Run JavaScript", "format": {"type": "text"}},
        ]}],
    }, None, None, None, bridge))
    call = response.output[-1]
    assert call.type == "function_call", "Inspect now restores custom calls. Delete CodexModel and this test."
    assert json.loads(call.arguments) == {"input": "text(42);"}


def test_codex_native_search_result_reaches_responses_client():
    reply = ModelOutput.from_content("mockllm/model", "Found ERC-8004.")
    reply.message.content = [ContentToolUse(tool_type="web_search", id="ws_proof", name="search",
                                          arguments='{"type":"search","query":"ERC-8004"}', result="Found ERC-8004.")]
    model = agents.CodexModel(get_model("mockllm/model", custom_outputs=[reply], memoize=False))
    bridge = AgentBridge(AgentState(messages=[]), model_aliases={"inspect": model})
    response = asyncio.run(inspect_responses_api_request_impl({
        "model": "inspect", "input": [{"role": "user", "content": "Find ERC-8004"}],
        "tools": [{"type": "web_search"}],
    }, None, None, None, bridge))
    search = response.output[0]
    assert (search.type, search.id, search.action.type, search.action.query) == (
        "web_search_call", "ws_proof", "search", "ERC-8004")


@pytest.mark.parametrize("requested", ["inspect", "gpt-5.5", "another-model", "openai/other"])
def test_codex_active_agent_adapts_every_bridge_model(tmp_path, requested, monkeypatch):
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
                "model": requested, "input": [{"role": "user", "content": "Run code"}],
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


def test_image_tag_changes_with_each_input(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "solc.json").write_text('{"version":"0.8.30"}\n')
    original = image_tag(tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM debian\n")
    changed = image_tag(tmp_path)
    (tmp_path / "solc.json").write_text('{"version":"0.8.31"}\n')
    assert len({original, changed, image_tag(tmp_path)}) == 3
