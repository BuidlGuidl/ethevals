"""Host-side search limits and credential handling without network."""
import json

import httpx
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match
from inspect_ai.solver import solver

from ethevals.search import web_search_exa


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
            tool = web_search_exa("https://mcp.exa.ai/mcp", 2)
            answers = [await tool("Ethereum") for _ in range(3)]
            state.output = ModelOutput.from_content("mockllm/model", json.dumps(answers))
            return state
        return solve

    log = eval(Task(dataset=[Sample(input="Search", target="Test")], solver=searches(), scorer=match(),
                    model="mockllm/model"), log_dir=str(tmp_path), display="none")[0]
    answers = json.loads(log.samples[0].output.completion)
    assert answers == ["Test result [redacted]"] * 2 + [
        "Search failed: epoch search rate limit exceeded."]
    assert requests == [(key, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "web_search_exa", "arguments": {"query": "Ethereum", "numResults": 5, "type": "auto"}}})] * 2
