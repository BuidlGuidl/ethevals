from support import fixture_config
from contextlib import contextmanager
from dataclasses import replace
from ethevals.checks import check_agent, check_grader
from ethevals.images.tag import image_tag
from ethevals.loader import load_eval
from ethevals.preparation import build_images, prepare_compose
from ethevals.rows import export_rows, results_rows
from ethevals.runner import build_task
from ethevals.sandboxes import IMAGES, runner_exec
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.solver import solver
from inspect_ai.util import sandbox
from pathlib import Path
import anyio
import json
import pytest
import subprocess
import time
import uuid


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]
IMAGE = image_tag(IMAGES, "chain")


def docker(*args, input=None, check=True, timeout=240):
    result = subprocess.run(["docker", *args], input=input, capture_output=True, text=True, timeout=timeout)
    if check:
        assert result.returncode == 0, result.stderr + result.stdout
    return result


@contextmanager
def chain_container():
    name = "chain-fixes-" + uuid.uuid4().hex[:12]
    try:
        docker("run", "-d", "--name", name, IMAGE)
        for _ in range(100):
            if docker("exec", name, "cast", "chain-id", "--rpc-url", "http://127.0.0.1:8545", check=False).returncode == 0:
                break
            time.sleep(.1)
        else:
            pytest.fail("Chain did not start")
        yield name
    finally:
        docker("rm", "-f", name)


def test_expensive_signed_transaction_cannot_change_captured_state():
    with chain_container() as name:
        source = Path(__file__).with_name("chain_mining_probe.py").read_text()
        result = docker("exec", "-i", name, "python3", "-", input=source)
        value = json.loads(result.stdout)
        assert value["boundary"] == value["before"] == value["after"]
        assert "result" in value["tx"]


def test_reference_and_scripts_have_internet_and_receive_setup_files(tmp_path):
    config = fixture_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    probe = b"import urllib.request; assert urllib.request.urlopen('https://example.com', timeout=15).status == 200\n"
    files = {**evaluation.files}
    files["scorer/setup.sh"] = files["scorer/setup.sh"].replace(b"set -euo pipefail", b"set -euo pipefail\npython3 -c \"" + probe.strip() + b"\"")
    files["scorer/check.py"] = files["scorer/check.py"].replace(b"import json", probe + b"import json")
    files["scorer/solution/run.sh"] = b"set -eu\ncurl --fail --silent --max-time 15 https://example.com >/dev/null\n" + files["scorer/solution/run.sh"]
    evaluation = replace(evaluation, files=files)
    compose = prepare_compose(evaluation, tmp_path)
    task = build_task(evaluation, config, check_agent(evaluation, "reference"), check_grader(), "internet", 1, compose)
    log = eval(task, log_dir=str(tmp_path / "online"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    assert row["status"] == "passed", row
    assert row["checks"]["script:recipient_balance"] == {"passed": True, "reason": "Recipient holds 12500000 base units; expected 12500000."}


def amd64_smoke(image):
    prefix = "chain-amd64-" + uuid.uuid4().hex[:12]
    chain, reference = prefix + "-chain", prefix + "-reference"
    fixture = ROOT / "evals/transactions/send-six-decimal-token"
    try:
        docker("network", "create", "--internal", "-o", "com.docker.network.bridge.inhibit_ipv4=true", prefix)
        docker("run", "-d", "--platform", "linux/amd64", "--network", prefix, "--network-alias", "chain", "--name", chain, image)
        docker("run", "-d", "--platform", "linux/amd64", "--network", prefix, "--name", reference, "--entrypoint", "sleep", image, "infinity")
        assert "forge Version: 1.5.1" in docker("exec", chain, "forge", "--version").stdout
        for _ in range(100):
            if docker("exec", chain, "cast", "chain-id", "--rpc-url", "http://127.0.0.1:8545", check=False).returncode == 0:
                break
            time.sleep(.1)
        docker("exec", chain, "mkdir", "-p", "/eval/scorer")
        for name in ("setup.sh", "check.py", "Token.sol"):
            docker("cp", str(fixture / "scorer" / name), chain + ":/eval/scorer/" + name)
        setup = json.loads(docker("exec", chain, "env", "RPC_URL=http://127.0.0.1:8546", "PUBLIC_RPC_URL=http://chain:8545", "SOLC=/opt/solc", "bash", "/eval/scorer/setup.sh").stdout)
        docker("exec", "-u", "root", reference, "mkdir", "/workspace")
        docker("exec", "-i", "-u", "root", reference, "bash", "-c", "cat > /workspace/chain.json", input=setup["files"]["chain.json"])
        docker("exec", "-i", "-w", "/workspace", reference, "bash", input=(fixture / "scorer/solution/run.sh").read_text())
        checks = json.loads(docker("exec", chain, "env", "RPC_URL=http://127.0.0.1:8546", "python3", "/eval/scorer/check.py").stdout)
        assert checks == {
            "recipient_balance": {"passed": True, "reason": "Recipient holds 12500000 base units; expected 12500000."},
            "agent_sender": {"passed": True, "reason": "One transaction came from the agent key."}}
        return {"checks": checks}
    finally:
        docker("rm", "-f", chain, reference, check=False)
        docker("network", "rm", prefix, check=False)


def test_clean_builder_needs_no_runner_image_and_amd64_smoke():
    name = "chain-builder-" + uuid.uuid4().hex[:12]
    image = "ethevals-chain:" + name
    try:
        docker("buildx", "create", "--name", name, "--driver", "docker-container")
        # A fresh container builder cannot access images in the host engine.
        docker("buildx", "build", "--builder", name, "--platform", "linux/amd64", "--no-cache", "--load",
               "-t", image, "-f", str(IMAGES / "Chain.Dockerfile"), str(IMAGES), timeout=600)
        assert docker("image", "inspect", image, "--format", "{{.Architecture}}").stdout.strip() == "amd64"
        assert amd64_smoke(image)["checks"]["recipient_balance"]["passed"] is True
    finally:
        docker("buildx", "rm", name, check=False)
        docker("image", "rm", image, check=False)


def test_broken_chain_build_reports_dockers_message(tmp_path, monkeypatch):
    import ethevals.preparation as preparation
    import shutil
    images = tmp_path / "images"
    shutil.copytree(IMAGES, images)
    (images / "Chain.Dockerfile").write_text(f"FROM {IMAGE}\nRUN echo chain-build-canary >&2; exit 73\n")
    monkeypatch.setattr(preparation, "IMAGES", images)
    with pytest.raises(RuntimeError, match="chain-build-canary"):
        preparation.build_images()


@solver
def slow_agent():
    async def solve(state, generate):
        await anyio.sleep(1)
        return await generate(state)
    return solve


def test_slow_setup_preserves_agent_time(tmp_path):
    config = fixture_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    files = {**evaluation.files,
             "scorer/setup.sh": b'#!/usr/bin/env python3\nimport time; time.sleep(31); print(\'{"files": {}}\')',
             "scorer/check.py": b'#!/usr/bin/env python3\nprint(\'{"ran":{"passed":true,"reason":"Agent reached grading."}}\')'}
    evaluation = replace(evaluation, files=files)
    compose = prepare_compose(evaluation, tmp_path)
    agent = replace(check_agent(evaluation, "empty"), solver_for=lambda _: slow_agent())
    task = build_task(evaluation, config, agent, check_grader(), "internet", 1, compose)
    task.working_limit = 2
    # Setup exceeds both agent limits. The wall limit also gives scoring
    # 15 seconds instead of a flaky one-second Docker capture deadline.
    task.time_limit = 30
    log = eval(task, log_dir=str(tmp_path / "slow"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    assert (row["status"], row["checks"]) == ("passed", {"script:ran": {"passed": True, "reason": "Agent reached grading."}})
    assert row["total_tokens"] > 0


@solver
def attempt(evaluation, variant):
    async def solve(state, generate):
        box = sandbox("default")
        source = evaluation.files["scorer/solution/run.sh"]
        if variant in {"reference", "wrong"}:
            if variant == "wrong":
                source = source.replace(b"125 * 10 ** decimals / 10", b"13 * 10 ** decimals")
            await box.write_file("/workspace/run.sh", source)
            result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], timeout=60)
            assert result.success, result.stderr
        elif variant == "crash":
            await sandbox("chain").write_file("/eval/scorer/check.py", b"#!/usr/bin/env python3\nraise RuntimeError('crash proof')\n")
        elif variant == "missing":
            await sandbox("chain").write_file("/eval/scorer/check.py", b'#!/usr/bin/env python3\nprint(\'{"recipient_balance":{"passed":false,"reason":"Missing sender proof."}}\')\n')
        elif variant == "cheat":
            result = await runner_exec(box, ["/bin/bash", "-c", """
set -eu
read_value() { sed -n 's/.*"'"$1"'": "\\([^"]*\\)".*/\\1/p' /workspace/chain.json; }
sender=$(read_value sender)
token=$(read_value token)
recipient=$(read_value recipient)
data=$(cast calldata 'transfer(address,uint256)' "$recipient" 12500000)
transaction="{\\"from\\":\\"$sender\\",\\"to\\":\\"$token\\",\\"data\\":\\"$data\\",\\"gas\\":\\"0x186a0\\"}"
for method in eth_sendTransaction eth_sendUnsignedTransaction; do
    curl -sS -H 'Content-Type: application/json' --data "{\\"jsonrpc\\":\\"2.0\\",\\"id\\":1,\\"method\\":\\"$method\\",\\"params\\":[$transaction]}" http://chain:8545
done
curl -sS -H 'Content-Type: application/json' --data "{\\"jsonrpc\\":\\"2.0\\",\\"id\\":1,\\"method\\":\\"anvil_setBalance\\",\\"params\\":[\\"$recipient\\",\\"0xffff\\"]}" http://chain:8545
curl -sS -H 'Content-Type: application/json' --data "[{\\"jsonrpc\\":\\"2.0\\",\\"id\\":1,\\"method\\":\\"eth_chainId\\"},{\\"jsonrpc\\":\\"2.0\\",\\"id\\":2,\\"method\\":\\"eth_sendUnsignedTransaction\\",\\"params\\":[$transaction]}]" http://chain:8545
curl -sS -H 'Connection: Upgrade' -H 'Upgrade: websocket' http://chain:8545
if curl -sS --connect-timeout 2 http://chain:8546; then exit 1; fi
"""])
            assert result.success, result.stderr
            assert result.stdout.count("-32601") == 5
            assert "405" in result.stdout
        elif variant == "pending":
            # Queue a signed future-nonce transfer. Capture must not mine it.
            source = source.replace(b"cast send \"$token\"", b"cast send --async --nonce 1 \"$token\"")
            await box.write_file("/workspace/run.sh", source)
            result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], timeout=60)
            assert result.success, result.stderr
            # Keep trying the valid transfer after the solver returns.
            await box.write_file("/workspace/run.sh", evaluation.files["scorer/solution/run.sh"])
            result = await runner_exec(box, ["/bin/bash", "-c", "nohup bash -c 'sleep 3; bash /workspace/run.sh' >/tmp/writer.log 2>&1 </dev/null &"])
            assert result.success
            original = evaluation.files["scorer/check.py"]
            probe = b"""#!/usr/bin/env python3
import sys, time
sys.path.insert(0, '/opt')
from rpc_filter import rpc
before = rpc('eth_getBlockByNumber', ['latest', False])['hash']
time.sleep(4)
assert rpc('eth_getBlockByNumber', ['latest', False])['hash'] == before
"""
            await sandbox("chain").write_file("/eval/scorer/check.py", probe + original)
        return await generate(state)
    return solve


def test_act_checks_bypasses_and_grading_boundary(tmp_path):
    output = tmp_path / "chain"
    config = fixture_config()
    root = Path(__file__).resolve().parents[2]
    evaluation = load_eval(root / "evals/transactions/send-six-decimal-token", config)
    build_images()
    compose = prepare_compose(evaluation, output)
    tasks = []
    variants = ("reference", "wrong", "crash", "missing", "cheat", "pending")
    for variant in variants:
        agent = check_agent(evaluation, "empty")
        agent = replace(agent, metadata={**agent.metadata, "epoch": list(variants).index(variant) + 1},
                         solver_for=lambda _, variant=variant: attempt(evaluation, variant))
        tasks.append(build_task(evaluation, config, agent, check_grader(), "internet", 1, compose))
    eval(tasks, log_dir=str(output / "logs"), display="plain", retry_on_error=0, fail_on_error=False, max_tasks=2)
    rows = export_rows(output)
    for row in rows:
        assert row["status"] == ("passed" if list(variants)[row["epoch"] - 1] == "reference" else
                                 "error" if list(variants)[row["epoch"] - 1] == "crash" else "failed"), row
        names = (set() if list(variants)[row["epoch"] - 1] == "crash" else
                 {"script:recipient_balance"} if list(variants)[row["epoch"] - 1] == "missing" else
                 {"script:agent_sender", "script:recipient_balance"})
        assert set(row["checks"]) == names
        if list(variants)[row["epoch"] - 1] == "wrong":
            assert row["checks"]["script:recipient_balance"] == {"passed": False, "reason": "Recipient holds 13000000 base units; expected 12500000."}
        if list(variants)[row["epoch"] - 1] == "pending":
            assert row["checks"]["script:recipient_balance"] == {"passed": False, "reason": "Recipient holds 0 base units; expected 12500000."}
        if list(variants)[row["epoch"] - 1] == "cheat":
            log = read_eval_log(str(output / row["log_file"]))
            text = log.model_dump_json()
            for method in ("eth_sendTransaction", "eth_sendUnsignedTransaction", "anvil_setBalance", "HTTP GET"):
                assert f"RPC refused: {method}" in text or f"RPC refused: '{method}'" in text
