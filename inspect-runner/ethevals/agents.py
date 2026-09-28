from inspect_ai.agent import as_solver
from inspect_ai.model import Model
from inspect_ai.solver import multiple_choice, solver
from inspect_ai.tool import MCPServerConfigHTTP
from inspect_swe import claude_code, codex_cli, opencode
import json
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Harness:
    factory: Callable
    version: str


def claude(config, model):
    servers = [MCPServerConfigHTTP(type="http", name="exa", url=config.search_provider)] if config.search_provider else []
    return as_solver(claude_code(
        cwd="/workspace", model_config=model.agent_model_config, effort=model.effort,
        version=AGENTS["claude_code"].version, disallowed_tools=["WebSearch"], mcp_servers=servers,
        retry_uncaught_errors=0,
    ))


def codex(config, model):
    servers = [MCPServerConfigHTTP(type="http", name="exa", url=config.search_provider)] if config.search_provider else []
    return as_solver(codex_cli(
        cwd="/workspace", model_config=model.agent_model_config,
        version=AGENTS["codex_cli"].version, web_search="disabled", mcp_servers=servers,
        config_overrides={"model_reasoning_effort": json.dumps(model.effort)},
        filter=codex_tool_types,
    ))


async def codex_tool_types(model: Model, messages, tools, tool_choice, config):
    # OpenRouter returns JSON function calls. Codex expects custom calls for
    # code-mode exec. Restore the type from the CLI's own tool declarations.
    output = await model.generate(messages, tools=tools, tool_choice=tool_choice, config=config)
    custom = {tool.name for tool in tools if tool.options and "custom_format" in tool.options}
    for choice in output.choices:
        for call in choice.message.tool_calls or []:
            if call.function in custom:
                call.type = "custom"
    return output


def open_code(config, model):
    servers = [MCPServerConfigHTTP(type="http", name="exa", url=config.search_provider)] if config.search_provider else []
    return as_solver(opencode(
        cwd="/workspace", version=AGENTS["opencode"].version, mcp_servers=servers,
        # This identifier selects the wire protocol. Inspect selects the real model
        # and supplies its configured reasoning effort through the bridge.
        opencode_model="anthropic/claude-sonnet-4-5",
        env={"OPENCODE_CONFIG_CONTENT": json.dumps({"tools": {"websearch": False}})},
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
    agent = AGENTS[harness].factory(config, model)

    async def solve(state, generate):
        if state.choices:
            async def invoke(state, **kwargs):
                return await agent(state, generate)
            return await multiple_choice()(state, invoke)
        return await agent(state, generate)
    return solve
