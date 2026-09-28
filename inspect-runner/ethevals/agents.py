from inspect_ai.agent import as_solver
from inspect_ai.solver import multiple_choice, solver
from inspect_ai.tool import MCPServerConfigHTTP
from inspect_swe import claude_code


HARNESS_VERSIONS = {"claude_code": "2.1.274"}


def claude(config, model):
    servers = [MCPServerConfigHTTP(type="http", name="exa", url=config.search_provider)] if config.search_provider else []
    return as_solver(claude_code(
        cwd="/workspace", model_config=model.agent_model_config, effort=model.effort,
        version=HARNESS_VERSIONS["claude_code"], disallowed_tools=["WebSearch"], mcp_servers=servers,
        retry_uncaught_errors=0,
    ))


# Step 3 adds Codex CLI and OpenCode factories here.
AGENTS = {"claude_code": claude}


@solver
def internet_solver(harness: str, config, model):
    if harness not in AGENTS:
        raise ValueError(f"Harness {harness!r} has no internet solver yet")
    agent = AGENTS[harness](config, model)

    async def solve(state, generate):
        if state.choices:
            async def invoke(state, **kwargs):
                return await agent(state, generate)
            return await multiple_choice()(state, invoke)
        return await agent(state, generate)
    return solve
