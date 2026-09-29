from inspect_ai.agent import as_solver, BridgedToolsSpec
from inspect_ai.model import Model
from inspect_ai.solver import multiple_choice, solver
from inspect_ai.util import sandbox
from inspect_swe import claude_code, codex_cli, opencode
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .skills import skill_index


@dataclass(frozen=True)
class Harness:
    factory: Callable
    version: str
    instructions: str

    def build(self, config, cli_model: str, skills=None):
        from .search import exa_tools
        # Codex code mode calls MCP from a script, outside a direct model tool proposal.
        # The host tool enforces the per-epoch request cap for every caller.
        bridges = [BridgedToolsSpec(name="exa", tools=exa_tools(config.search_limit),
                                   require_proposal=False)] if config.search else []
        return self.factory(cli_model, version=self.version, bridged_tools=bridges, skills=skills)


def claude(cli_model: str, **settings):
    return as_solver(claude_code(
        cwd="/workspace", model_config=cli_model,
        disallowed_tools=["WebSearch"], retry_refusals=0, retry_uncaught_errors=0,
        **settings,
    ))


def codex(cli_model: str, **settings):
    # The active agent is a CodexModel, so every bridge fallback uses it.
    return as_solver(codex_cli(
        cwd="/workspace", model_config=cli_model,
        web_search="disabled", retry_refusals=0,
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


def open_code(cli_model: str, **settings):
    provider = json.loads((Path(__file__).with_name("images") / "opencode-models.json").read_text())
    return as_solver(opencode(
        cwd="/workspace", retry_refusals=0, opencode_model=cli_model,
        env={"OPENROUTER_API_KEY": "sk-none",
             "OPENCODE_CONFIG_CONTENT": json.dumps({"provider": {"openrouter": provider}})},
        **settings,
    ))


HARNESSES = {
    "claude_code": Harness(claude, "2.1.274", "CLAUDE.md"),
    "codex_cli": Harness(codex, "0.158.0", "AGENTS.md"),
    "opencode": Harness(open_code, "1.18.33", "AGENTS.md"),
}


@solver
def internet_solver(config, agent, skills=None):
    harness = HARNESSES[agent.harness]
    run_agent = harness.build(config, agent.cli_model, skills)

    async def solve(state, generate):
        if skills:
            path = "/workspace/" + harness.instructions
            try:
                existing = await sandbox().read_file(path)
            except FileNotFoundError:
                existing = ""
            await sandbox().write_file(path, "\n\n".join(filter(None, [existing, skill_index(skills)])))
        if state.choices:
            async def invoke(state, **kwargs):
                return await run_agent(state, generate)
            return await multiple_choice()(state, invoke)
        return await run_agent(state, generate)
    return solve
