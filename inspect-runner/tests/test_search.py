"""Host-side search limits and credential handling without network."""
import json
import zipfile

import httpx
import pytest
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match
from inspect_ai.solver import solver

from ethevals.search import exa_tools


def test_search_cap_has_its_own_row_counter():
    from inspect_ai.log import EvalSample
    from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
    from inspect_ai.tool import ToolCall
    from ethevals.rows import search_failures
    sample = EvalSample(id="search", epoch=1, input="", target="", messages=[
        ChatMessageAssistant(content="", tool_calls=[ToolCall(id="1", function="web_fetch_exa", arguments={}),
                                                    ToolCall(id="2", function="web_search_exa", arguments={})]),
        ChatMessageTool(content="Search failed: epoch search cap reached.", tool_call_id="1"),
        ChatMessageTool(content="Search failed: Exa rate limit exceeded.", tool_call_id="2"),
    ])
    assert search_failures(sample) == {"search_calls": 2, "search_failed": 2, "search_rate_limited": 1, "search_capped": 1}


@pytest.mark.docker
def test_bridge_matches_keyless_hosted_tools():
    from inspect_ai.tool import ToolDef
    response = httpx.post("https://mcp.exa.ai/mcp", headers={"Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, timeout=30)
    response.raise_for_status()
    payload = next(json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:"))
    hosted = payload["result"]["tools"]
    tools = [ToolDef(tool) for tool in exa_tools("https://mcp.exa.ai/mcp", 20)]
    assert [tool.name for tool in tools] == ["web_search_exa", "web_fetch_exa"]
    for actual, expected in zip(tools, hosted, strict=True):
        assert actual.name == expected["name"]
        assert actual.description == expected["description"]
        from inspect_ai.tool import ToolParams
        assert actual.parameters.model_dump() == ToolParams.model_validate(expected["inputSchema"]).model_dump()


def test_host_search_caps_requests_and_redacts_credentials(tmp_path, monkeypatch):
    import ethevals.search as search
    key = "inert-offline-exa-canary"
    monkeypatch.setenv("EXA_API_KEY", key)
    requests = []

    def transport(request):
        requests.append((request.headers.get("x-api-key"), json.loads(request.content)))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": "Test result " + key}]}})

    client = httpx.AsyncClient
    monkeypatch.setattr(search.httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(transport), **kw))

    @solver
    def searches():
        async def solve(state, generate):
            search, fetch = exa_tools("https://mcp.exa.ai/mcp", 2)
            answers = [await search(query="Ethereum", objective="Find the protocol spec"),
                       await fetch(urls=["https://ethereum.org"]),
                       await search(query="Ethereum", objective="Find the protocol spec")]
            state.output = ModelOutput.from_content("mockllm/model", json.dumps(answers))
            return state
        return solve

    log = eval(Task(dataset=[Sample(input="Search", target="Test")], solver=searches(), scorer=match(),
                    model="mockllm/model"), log_dir=str(tmp_path), display="none")[0]
    answers = json.loads(log.samples[0].output.completion)
    assert answers == ["Test result [redacted]"] * 2 + [
        "Search failed: epoch search cap reached."]
    assert requests == [(key, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}) for params in [
        {"name": "web_search_exa", "arguments": {"query": "Ethereum", "objective": "Find the protocol spec"}},
        {"name": "web_fetch_exa", "arguments": {"urls": ["https://ethereum.org"]}}]]
    archives = list(tmp_path.glob("*.eval"))
    assert len(archives) == 1
    for path in archives:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                assert key.encode() not in archive.read(name), name


@pytest.mark.parametrize("status,answer", [(401, "Search failed: Exa request failed."),
                                         (429, "Search failed: Exa rate limit exceeded.")])
def test_exa_http_failure_logs_status_without_credentials(tmp_path, monkeypatch, caplog, status, answer):
    import ethevals.search as search
    key = "inert-offline-exa-canary"
    monkeypatch.setenv("EXA_API_KEY", key)
    client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=key))
    monkeypatch.setattr(search.httpx, "AsyncClient", lambda **kw: client(transport=transport, **kw))

    @solver
    def failed_search():
        async def solve(state, generate):
            result = await exa_tools("https://mcp.exa.ai/mcp", 2)[0](query="Ethereum", objective="Find the spec")
            state.output = ModelOutput.from_content("mockllm/model", result)
            return state
        return solve

    log = eval(Task(dataset=[Sample(input="Search", target="Test")], solver=failed_search(), scorer=match(),
                    model="mockllm/model"), log_dir=str(tmp_path), display="none")[0]
    assert log.samples[0].output.completion == answer
    assert f"Exa HTTP status {status}" in caplog.text
    assert key not in caplog.text
