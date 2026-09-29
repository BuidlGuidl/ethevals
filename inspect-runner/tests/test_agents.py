import asyncio
import json
import inspect
from pathlib import Path
import yaml

import pytest
from pydantic import ValidationError
from inspect_ai.model import ChatMessageUser, GenerateConfig, ModelOutput, get_model
from inspect_ai.tool import ToolInfo
from inspect_ai.util import ExecResult
from inspect_ai.agent import AgentState
from inspect_ai.agent._bridge.types import AgentBridge
from inspect_ai.agent._bridge.util import bridge_generate, in_bridge_model_generate
from inspect_ai.agent._bridge.responses_impl import (
    inspect_responses_api_request_impl, responses_output_items_from_assistant_message, tools_from_responses_tool,
)
from inspect_ai.model._openai import chat_tool_calls_from_openai
from openai.types.chat import ChatCompletionMessage
from inspect_swe._codex_cli._events.consumer import CodexConsumer

from ethevals import agents
from ethevals.actors import player
from ethevals.config import Config, load_config
from ethevals.images.tag import image_tag
from test_contracts import scoring_case, YES


@pytest.mark.parametrize("key,harness", [
    ("opus", "claude_code"), ("codex", "codex_cli"),
    ("kimi", "opencode"), ("glm", "opencode"),
])
def test_registry_builds_solver(key, harness):
    config = load_config()
    for search in ["https://example.org/search", None]:
        config.search_provider = search
        solve = agents.AGENTS[harness].build(config, config.models[key])
        assert inspect.iscoroutinefunction(solve)
        assert list(inspect.signature(solve).parameters) == ["state", "generate"]


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


@pytest.mark.parametrize("requested", ["inspect", "gpt-6-sol", "another-model", "openai/other"])
def test_codex_active_player_adapts_every_bridge_model(tmp_path, requested, monkeypatch):
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import solver
    config = load_config()
    config.models["codex"].model = "mockllm/model"
    actor = player(config, "codex", "internet")
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


@pytest.mark.parametrize("local_oom,code,status", [
    (True, 137, "failed"), (False, 137, "error"), (True, 1, "error"), (True, 0, "passed")])
@pytest.mark.parametrize("cli_name", ["claude code", "codex cli", "opencode"])
def test_agent_failure_exports_memory_cause(scoring_case, monkeypatch, local_oom, code, status, cli_name):
    config = load_config()

    class Box:
        reads = 0
        async def exec(self, command, **kwargs):
            if "/sys/fs/cgroup/memory.peak" in command:
                return ExecResult(success=True, returncode=0, stdout="134217728\n", stderr="")
            self.reads += 1
            return ExecResult(success=True, returncode=0, stdout=(
                "oom 4\noom_kill 4\n" if self.reads == 1 else
                f"oom {5 if local_oom else 4}\noom_kill 5\n"), stderr="")

    async def killed(state, generate):
        if code == 0:
            return state
        raise RuntimeError(f"Error executing {cli_name} agent {code}: CLI failure")

    monkeypatch.setitem(agents.AGENTS, "proof", agents.Harness(lambda *a, **kw: killed, "proof"))
    monkeypatch.setattr(agents, "sandbox", lambda name: box)
    box = Box()
    scoring_case["task"].solver = agents.internet_solver("proof", config, config.models["opus"])
    row = scoring_case["run"]([YES, YES] if code == 0 else [])
    assert (row["status"], row["passed"]) == (status, None if status == "error" else status == "passed")
    assert row["agent_memory_peak_bytes"] == 134217728
    if status == "failed":
        assert {check["reason"] for check in row["checks"].values()} == {"Agent exceeded its container memory limit."}
    elif status == "error":
        assert f"Error executing {cli_name} agent {code}" in row["error_reason"]
