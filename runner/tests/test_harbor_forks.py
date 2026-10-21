import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib
import uuid

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "runner/ethevals/images"
pytestmark = pytest.mark.docker


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture(scope="module")
def chain_tools():
    image = "ethevals-harbor-fork-proof:local"
    docker("build", "--target", "tools", "--file", str(IMAGES / "Chain.Dockerfile"),
           "--tag", image, str(IMAGES))
    return image


def test_pinned_fork_keeps_its_secret_out_of_setup_agent_and_logs(tmp_path, monkeypatch, chain_tools):
    name = "harbor-upstream-" + uuid.uuid4().hex[:12]
    docker("network", "create", name)
    try:
        docker("run", "-d", "--name", name, "--network", name, "--network-alias", "upstream",
               "--memory", "256m", "--entrypoint", "anvil", chain_tools,
               "--host", "0.0.0.0", "--chain-id", "8453", "--accounts", "0", "--silent")
        for _ in range(50):
            try:
                docker("exec", name, "cast", "chain-id")
                break
            except subprocess.CalledProcessError:
                time.sleep(0.1)
        docker("exec", name, "cast", "rpc", "anvil_setBalance", "0x0000000000000000000000000000000000001234",
               "0x6124fee993bc0000")
        docker("exec", name, "cast", "rpc", "evm_mine")
        docker("exec", name, "cast", "rpc", "evm_mine")
        docker("exec", name, "cast", "rpc", "anvil_setBalance", "0x0000000000000000000000000000000000001234",
               "0x7ce66c50e2840000")
        docker("exec", name, "cast", "rpc", "evm_mine")
        source = next(path.parent.parent for path in (ROOT / "tasks").rglob("environment/docker-compose.yaml")
                      if "chain" in yaml.safe_load(path.read_text())["services"]
                      and not tomllib.loads((path.parent.parent / "task.toml").read_text())
                      .get("metadata", {}).get("required_env"))
        task = tmp_path / "fork"
        shutil.copytree(source, task)
        settings = task / "task.toml"
        settings.write_text(settings.read_text().replace(
            "[metadata]", '[metadata]\nrequired_env = ["ARCHIVE_RPC_URL"]'))
        compose = task / "environment/docker-compose.yaml"
        document = yaml.safe_load(compose.read_text())
        document["services"]["chain"]["environment"] = {
            "FORK_RPC_URL": "${ARCHIVE_RPC_URL:?ARCHIVE_RPC_URL is required}", "FORK_BLOCK_NUMBER": "1"}
        document["services"]["chain"]["networks"] = ["default", "upstream"]
        document["networks"] = {"default": {}, "upstream": {"external": True, "name": name}}
        compose.write_text(yaml.safe_dump(document))
        setup = task / "environment/setup/setup.s.sol"
        setup.write_text(setup.read_text().replace("function run() external {", '''function run() external {
        require(!vm.envExists("FORK_RPC_URL"), "setup received the fork secret");
        require(!vm.envExists("ARCHIVE_RPC_URL"), "setup received the host secret");
        require(address(0x1234).balance == 7 ether, "fork uses the pinned upstream state");'''))
        (task / "tests/Pinned.t.sol").write_text('''pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
contract PinnedCheck is Test {
    function test_pinned_upstream_state() public {
        vm.createSelectFork("chain");
        assertEq(address(0x1234).balance, 7 ether, "fork keeps the pinned upstream balance");
    }
}
''')
        (task / "solution/probe.py").write_text('''import json
import os
from pathlib import Path
import urllib.request
context = json.loads(Path("/workspace/chain_context.json").read_text())
payload = {"jsonrpc": "2.0", "id": 1, "method": "anvil_nodeInfo", "params": []}
request = urllib.request.Request(context["rpcUrl"], json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
with urllib.request.urlopen(request) as response:
    refusal = json.load(response)
Path("/logs/agent/fork-proof.json").write_text(json.dumps({
    "chain_id": context["chainId"], "rpc_url": context["rpcUrl"],
    "secret_env": sorted(name for name in os.environ if name in {"ARCHIVE_RPC_URL", "FORK_RPC_URL"}),
    "node_info": refusal,
}))
''')
        solve = task / "solution/solve.sh"
        solve.write_text(solve.read_text().replace("set -eu", "set -eu\npython3 /solution/probe.py"))
        marker = "FORK_SECRET_PROBE_94f7"
        monkeypatch.setenv("ARCHIVE_RPC_URL", f"http://upstream:8545/?key={marker}")
        output = tmp_path / "job"
        result = subprocess.run([sys.executable, "-m", "ethevals.cli", "free-check", "--tasks", str(task),
                                 "--output", str(output)], capture_output=True, text=True, timeout=900)
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(next((output / "oracle").glob("*/agent/fork-proof.json")).read_text())
        assert proof == {"chain_id": 8453, "rpc_url": "http://chain:8545", "secret_env": [],
                         "node_info": {"jsonrpc": "2.0", "id": 1, "error": {
                             "code": -32601, "message": "Method is not allowed."}}}
        for agent, reward in (("oracle", 1), ("nop", 0)):
            trial = next((output / agent).glob("*/result.json"))
            record = json.loads(trial.read_text())
            assert record["verifier_result"]["rewards"] == {"reward": reward}
            checks = json.loads((trial.parent / "verifier/checks.json").read_text())
            assert checks["test_pinned_upstream_state"] == {"passed": True, "reason": "Test passed."}
        assert marker not in result.stdout + result.stderr
        saved = [path.read_bytes() for path in output.rglob("*") if path.is_file()]
        assert saved
        assert all(marker.encode() not in content and b"http://upstream:8545" not in content for content in saved)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        docker("network", "rm", name)


def test_anvil_startup_failure_does_not_log_the_upstream_url(chain_tools):
    marker = "FORK_STARTUP_SECRET_19c4"
    result = subprocess.run([
        "docker", "run", "--rm", "--network", "none", "--env", f"FORK_RPC_URL=http://unreachable.invalid/{marker}",
        "--env", "FORK_BLOCK_NUMBER=1", "--entrypoint", "python3", chain_tools, "/opt/rpc_filter.py",
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert "Anvil exited during startup." in result.stderr
    assert marker not in result.stdout + result.stderr
    assert "unreachable.invalid" not in result.stdout + result.stderr


def test_setup_failure_redacts_output_and_gets_no_fork_secret(tmp_path, chain_tools):
    url = "https://archive.example/setup-secret-probe"
    (tmp_path / "setup").mkdir()
    anvil = tmp_path / "anvil"
    anvil.write_text('''#!/usr/bin/python3
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": "0x1"}).encode())
    def log_message(self, *args):
        pass
HTTPServer(("127.0.0.1", 8546), Handler).serve_forever()
''')
    forge = tmp_path / "forge"
    forge.write_text(f'''#!/bin/sh
test -z "${{FORK_RPC_URL:-}}" || {{ echo "setup received a secret"; exit 3; }}
echo "setup stdout: {url}"
echo "setup stderr: {url}/" >&2
exit 1
''')
    anvil.chmod(0o755)
    forge.chmod(0o755)
    result = subprocess.run([
        "docker", "run", "--rm", "--user", "root", "--env", f"FORK_RPC_URL={url}",
        "--env", "FORK_BLOCK_NUMBER=1", "--volume", f"{tmp_path}:/probe:ro",
        "--volume", f"{tmp_path / 'setup'}:/setup:ro", "--entrypoint", "sh", chain_tools,
        "-c", 'PATH="/probe:$PATH" python3 /opt/start_chain.py',
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode == 1
    assert result.stdout == "setup stdout: <fork rpc>\nsetup stderr: <fork rpc>\n"
    assert "returned non-zero exit status 1" in result.stderr
    assert "setup received a secret" not in result.stdout + result.stderr
    assert "setup-secret-probe" not in result.stdout + result.stderr
