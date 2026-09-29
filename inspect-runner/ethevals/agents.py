from inspect_ai.agent import as_solver, BridgedToolsSpec
from inspect_ai.model import Model
from inspect_ai.solver import multiple_choice, solver
from inspect_swe import claude_code, codex_cli, opencode
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from inspect_ai.util import sandbox
from .sandboxes import memory_events, oom_killed


@dataclass(frozen=True)
class Harness:
    factory: Callable
    version: str

    def build(self, config, model):
        from .search import exa_tools
        # Codex code mode calls MCP from a script, outside a direct model tool proposal.
        # The host tool enforces the per-epoch request cap for every caller.
        bridges = [BridgedToolsSpec(name="exa", tools=exa_tools(config.search_provider, config.search_limit),
                                   require_proposal=False)] if config.search_provider else []
        return self.factory(model, version=self.version, bridged_tools=bridges)


def claude(model, **settings):
    return as_solver(claude_code(
        cwd="/workspace", model_config=model.agent_model_config, effort=model.effort,
        disallowed_tools=["WebSearch"], retry_refusals=0, retry_uncaught_errors=0,
        env={"CLAUDE_CODE_EFFORT_LEVEL": model.effort}, **settings,
    ))


def codex(model, **settings):
    # The active player is a CodexModel, so every bridge fallback uses it.
    return as_solver(codex_cli(
        cwd="/workspace", model_config=model.agent_model_config,
        web_search="disabled", retry_refusals=0,
        config_overrides={"model_reasoning_effort": json.dumps(model.effort)},
        **settings,
    ))


class CodexModel(Model):
    """Restore custom calls inside the bridge's normal generation context."""

    def __init__(self, source):
        super().__init__(source.api, source.config, source.model_args)
        self.source = source

    async def generate(self, input, tools=(), **kwargs):
        output = await self.source.generate(input, tools=tools, **kwargs)
        return restore_codex_calls(output, tools)


def restore_codex_calls(output, tools):
    # Inspect 0.3.271 forwards namespaced custom tools to non-OpenAI providers,
    # but never restores their custom reply type. Keep malformed calls recoverable.
    custom = {tool.name for tool in tools if tool.options
              and (tool.options.get("__responses_namespace__") or [None])[0] == "functions"
              and "custom_format" in tool.options}
    for choice in output.choices:
        for call in choice.message.tool_calls or []:
            if (call.function in custom and not call.parse_error
                    and set(call.arguments) == {"input"}
                    and isinstance(call.arguments["input"], str)):
                call.type = "custom"
    return output


def open_code(model, **settings):
    provider = json.loads((Path(__file__).with_name("images") / "opencode-models.json").read_text())
    for definition in provider["models"].values():
        definition["options"] = {"reasoning": {"effort": model.effort}}
    return as_solver(opencode(
        cwd="/workspace", retry_refusals=0, opencode_model=model.agent_model_config,
        env={"OPENROUTER_API_KEY": "sk-none",
             "OPENCODE_CONFIG_CONTENT": json.dumps({"provider": {"openrouter": provider}})},
        **settings,
    ))


AGENTS = {
    "claude_code": Harness(claude, "2.1.274"),
    "codex_cli": Harness(codex, "0.158.0"),
    "opencode": Harness(open_code, "1.18.33"),
}


@solver
def internet_solver(harness: str, config, model):
    if harness not in AGENTS:
        raise ValueError(f"Harness {harness!r} has no internet solver yet")
    agent = AGENTS[harness].build(config, model)

    async def solve(state, generate):
        box = sandbox("default")
        before = await memory_events(box)
        try:
            if state.choices:
                async def invoke(state, **kwargs):
                    return await agent(state, generate)
                return await multiple_choice()(state, invoke)
            return await agent(state, generate)
        except Exception:
            if not await oom_killed(box, before):
                raise
            state.metadata["agent_oom"] = True
            return state
    return solve
