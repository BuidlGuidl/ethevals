"""Regressions for the chain's mining, network, and setup boundaries."""
import json
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import anyio
import pytest
from inspect_ai import eval
from inspect_ai.solver import solver

from ethevals.checks import check_player, check_grader
from support import fixture_config
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.runner import build_task
from ethevals.rows import results_rows
from ethevals.sandboxes import IMAGES
from ethevals.images.tag import image_tag

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
    task = build_task(evaluation, config, check_player(evaluation, "reference"), check_grader(), "internet", 1, compose)
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
def slow_player():
    async def solve(state, generate):
        await anyio.sleep(1)
        return await generate(state)
    return solve


def test_slow_setup_preserves_player_time(tmp_path):
    config = fixture_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    files = {**evaluation.files,
             "scorer/setup.sh": b'#!/usr/bin/env python3\nimport time; time.sleep(31); print(\'{"files": {}}\')',
             "scorer/check.py": b'#!/usr/bin/env python3\nprint(\'{"ran":{"passed":true,"reason":"Player reached grading."}}\')'}
    evaluation = replace(evaluation, files=files)
    compose = prepare_compose(evaluation, tmp_path)
    player = replace(check_player(evaluation, "empty"), solver_for=lambda _: slow_player())
    task = build_task(evaluation, config, player, check_grader(), "internet", 1, compose)
    task.working_limit = 2
    # Setup exceeds both player limits. The wall limit also gives scoring
    # 15 seconds instead of a flaky one-second Docker capture deadline.
    task.time_limit = 30
    log = eval(task, log_dir=str(tmp_path / "slow"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    assert (row["status"], row["checks"]) == ("passed", {"script:ran": {"passed": True, "reason": "Player reached grading."}})
    assert row["total_tokens"] > 0
