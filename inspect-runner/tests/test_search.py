import json

from ethevals.search import exa_tools
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match
from inspect_ai.solver import solver
import httpx
import zipfile


def test_host_search_caps_requests_and_redacts_credentials(tmp_path, monkeypatch):
    import ethevals.search as search
    key = "inert-offline-exa-canary"
    monkeypatch.setenv("EXA_API_KEY", key)
    requests = []

    def transport(request):
        requests.append((request.headers.get("x-api-key"), json.loads(request.content)))
        if requests[-1][1]["params"]["name"] == "web_fetch_exa":
            return httpx.Response(200, json={"error": {"code": -32001, "message": "Rejected key " + key}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": "Test result " + key}]}})

    client = httpx.AsyncClient
    monkeypatch.setattr(search.httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(transport), **kw))

    @solver
    def searches():
        async def solve(state, generate):
            search, fetch = exa_tools(2)
            answers = [await search(query="Ethereum", objective="Find the protocol spec"),
                       await fetch(urls=["https://ethereum.org"]),
                       await search(query="Ethereum", objective="Find the protocol spec")]
            state.output = ModelOutput.from_content("mockllm/model", json.dumps(answers))
            return state
        return solve

    log = eval(Task(dataset=[Sample(input="Search", target="Test")], solver=searches(), scorer=match(),
                    model="mockllm/model"), log_dir=str(tmp_path), display="none")[0]
    answers = json.loads(log.samples[0].output.completion)
    assert answers == ["Test result [redacted]", "Search failed: Search failed at Exa.",
        "Search failed: epoch search cap reached."]
    assert requests == [(key, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}) for params in [
        {"name": "web_search_exa", "arguments": {"query": "Ethereum", "objective": "Find the protocol spec", "numResults": 10}},
        {"name": "web_fetch_exa", "arguments": {"urls": ["https://ethereum.org"]}}]]
    archives = list(tmp_path.glob("*.eval"))
    assert len(archives) == 1
    for path in archives:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                assert key.encode() not in archive.read(name), name


def test_search_clamps_results_and_rejects_large_fetch_batches(tmp_path, monkeypatch):
    import ethevals.search as search
    requests = []
    async def request(url, name, arguments, key):
        requests.append((name, arguments))
        return {"content": [{"type": "text", "text": "Fetched within the cap."}]}
    monkeypatch.setattr(search, "exa_request", request)

    @solver
    def capped():
        async def solve(state, generate):
            search, fetch = exa_tools(20)
            answers = [await search(query="Ethereum", objective="Find specs", numResults=200),
                       await search(query="Ethereum", objective="Find specs", numResults=-2),
                       await fetch(urls=["https://ethereum.org"] * 6),
                       await fetch(urls=["https://ethereum.org"] * 5)]
            state.output = ModelOutput.from_content("mockllm/model", json.dumps(answers))
            return state
        return solve
    log = eval(Task(dataset=[Sample(input="Search", target="")], solver=capped(), model="mockllm/model"),
               log_dir=str(tmp_path), display="none")[0]
    assert json.loads(log.samples[0].output.completion) == ["Fetched within the cap.", "Fetched within the cap.",
        "Search failed: at most 5 URLs are allowed per call.", "Fetched within the cap."]
    assert requests == [
        ("web_search_exa", {"query": "Ethereum", "objective": "Find specs", "numResults": 10}),
        ("web_search_exa", {"query": "Ethereum", "objective": "Find specs", "numResults": 1}),
        ("web_fetch_exa", {"urls": ["https://ethereum.org"] * 5})]
