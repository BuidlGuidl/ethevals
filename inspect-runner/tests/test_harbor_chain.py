import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.docker
def test_sidecar_controls_and_context_access_before_verification(tmp_path):
    source = next(path.parent.parent for path in (ROOT / "tasks").rglob("environment/docker-compose.yaml")
                  if "chain" in yaml.safe_load(path.read_text())["services"])
    task = tmp_path / "transfer"
    shutil.copytree(source, task)
    compose = task / "environment/docker-compose.yaml"
    document = yaml.safe_load(compose.read_text())
    for service in document["services"].values():
        service["build"]["context"] = str(ROOT / "inspect-runner/ethevals/images")
    compose.write_text(yaml.safe_dump(document))
    probe = '''import json
from pathlib import Path
import socket
import urllib.request

context = json.loads(Path('/workspace/chain_context.json').read_text())
url = context['rpcUrl']
def request(payload):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        return json.load(response)
def call(method):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': []}
methods = ['anvil_setBalance', 'evm_setAutomine', 'hardhat_reset', 'debug_setHead',
           'eth_sendTransaction', 'unknown_control']
refusals = {method: request(call(method))['error']['code'] for method in methods}
batch = request([call('eth_chainId'), call('anvil_setBalance')])
try:
    Path('/private/private_chain_context.json').read_text()
    private = 'readable'
except PermissionError:
    private = 'denied'
try:
    Path('/chain/chain_context.json').write_text('{}')
    public_write = 'writable'
except OSError:
    public_write = 'denied'
try:
    socket.create_connection(('chain', 8546), timeout=2).close()
    upstream = 'reachable'
except OSError:
    upstream = 'denied'
Path('/logs/agent/sidecar-proof.json').write_text(json.dumps({
    'public': int(request(call('eth_chainId'))['result'], 16) == context['chainId'],
    'private': private, 'public_write': public_write, 'upstream': upstream,
    'refusals': refusals, 'batch': [item['error']['code'] for item in batch],
    'setup_visible': Path('/setup').exists(), 'tests_visible': Path('/tests').exists(),
}))
'''
    (task / "solution/probe.py").write_text(probe)
    solve = task / "solution/solve.sh"
    solve.write_text(solve.read_text().replace("set -eu", "set -eu\npython3 /solution/probe.py"))
    output = tmp_path / "job"
    result = subprocess.run([sys.executable, "-m", "ethevals.cli", "free-check", "--tasks", str(task),
                             "--output", str(output)], capture_output=True, text=True, timeout=900)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "criteria skipped in the free check" in result.stdout
    proof = json.loads(next((output / "oracle").glob("*/agent/sidecar-proof.json")).read_text())
    assert proof == {
        "public": True, "private": "denied", "public_write": "denied", "upstream": "denied",
        "refusals": {method: -32601 for method in [
            "anvil_setBalance", "evm_setAutomine", "hardhat_reset", "debug_setHead",
            "eth_sendTransaction", "unknown_control"]},
        "batch": [-32601, -32601], "setup_visible": False, "tests_visible": False,
    }
    for agent, reward in (("oracle", 1), ("nop", 0)):
        trial = next((output / agent).glob("*/result.json"))
        record = json.loads(trial.read_text())
        assert record["verifier_environment_mode"] == "shared"
        assert record["verifier_result"]["rewards"] == {"reward": reward}
        checks = json.loads((trial.parent / "verifier/checks.json").read_text())
        assert checks["compile"] == {"passed": True, "reason": "Compilation passed."}
        assert all(check["passed"] for check in checks.values()) == bool(reward)
