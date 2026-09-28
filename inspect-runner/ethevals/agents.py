from inspect_ai.agent import as_solver
from inspect_ai.solver import multiple_choice, solver
from inspect_ai.tool import MCPServerConfigHTTP
from inspect_swe import claude_code


def claude(config, effort):
    servers = [MCPServerConfigHTTP(type="http", name="exa", url=config.search_provider)] if config.search_provider else []
    return as_solver(claude_code(
        cwd="/workspace", model_config="claude-opus-5-5", effort=effort,
        version="2.1.274", disallowed_tools=["WebSearch"], mcp_servers=servers,
        retry_uncaught_errors=0,
    ))


# Step 3 adds Codex CLI and OpenCode factories here.
AGENTS = {"claude_code": claude}


@solver
def internet_solver(harness: str, config, effort):
    if harness not in AGENTS:
        raise ValueError(f"Harness {harness!r} has no internet solver yet")
    agent = AGENTS[harness](config, effort)

    async def solve(state, generate):
        if state.choices:
            async def invoke(state, **kwargs):
                return await agent(state, generate)
            return await multiple_choice()(state, invoke)
        return await agent(state, generate)
    return solve
