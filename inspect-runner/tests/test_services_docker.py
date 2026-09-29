from dataclasses import replace
import json
import shutil
import subprocess
import uuid

from ethevals.images.tag import image_tag
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.runner import run
from ethevals.sandboxes import runner_exec
from ethevals.scorers import FORGE_SECONDS, forge, prepare_forge
import anyio
import pytest
import yaml

from conftest import fixture_config
from test_chain_docker import ROOT, docker
from test_forge_docker import DockerBox


pytestmark = pytest.mark.docker


def test_extra_service_online_forge_and_private_rpc(tmp_path):
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    extra = {"services": {"catalog": {"image": image_tag(image="chain"), "mem_limit": "96m",
             "entrypoint": ["python3"], "command": ["-m", "http.server", "8080"]}}}
    evaluation = replace(evaluation, files={**evaluation.files, "compose.yaml": yaml.safe_dump(extra).encode()})
    path = prepare_compose(evaluation, tmp_path)
    compose = ("compose", "-p", "services-" + uuid.uuid4().hex[:12], "-f", str(path))
    try:
        docker(*compose, "up", "-d", "--wait")
        response = docker(*compose, "exec", "-T", "default", "curl", "--fail", "--retry", "5",
                          "--retry-connrefused", "http://catalog:8080")
        assert "Directory listing for /" in response.stdout
        assert docker(*compose, "exec", "-T", "default", "cast", "chain-id",
                      "--rpc-url", "http://chain:8545").stdout.strip() == "31337"
        for method in ("anvil_setBalance", "evm_mine", "hardhat_setBalance"):
            result = docker(*compose, "exec", "-T", "default", "cast", "rpc", method,
                            "--rpc-url", "http://chain:8545", check=False)
            assert result.returncode != 0 and "-32601" in result.stderr
        blocked = docker(*compose, "exec", "-T", "default", "curl", "--connect-timeout", "2",
                         "--max-time", "3", "http://chain:8546", check=False)
        assert blocked.returncode == 7 and "Failed to connect" in blocked.stderr
        networks = json.loads(docker("inspect", docker(*compose, "ps", "-q", "catalog").stdout.strip()).stdout)[0]
        assert len(networks["NetworkSettings"]["Networks"]) == 1
        box = DockerBox(docker(*compose, "ps", "-q", "scorer").stdout.strip())

        async def proof():
            from ethevals.check_script import run_solution
            reference = replace(evaluation, files={"scorer/solution/source": b"new", "workspace/source": b"old"})
            await run_solution(reference, box)
            assert await box.read_file("/workspace/source") == "new"
            reference = replace(reference, files={**reference.files, "scorer/solution/run.sh": b"cp source copied\n"})
            await run_solution(reference, box)
            assert await box.read_file("/workspace/copied") == "new"
            online = await runner_exec(box, ["curl", "--fail", "--silent", "--max-time", "15", "https://example.com"])
            assert online.success and "Example Domain" in online.stdout
            installed = await runner_exec(box, ["sh", "-c", "sha256sum /home/agent/.svm/*/solc-*"])
            test = b'''pragma solidity =0.8.30;
interface Vm { function createSelectFork(string calldata) external returns (uint256); }
contract OnlineTest {
    function testPublicRpc() public {
        Vm(address(uint160(uint256(keccak256("hevm cheat code"))))).createSelectFork("https://ethereum.publicnode.com");
        require(block.chainid == 1);
    }
}'''
            await prepare_forge(box, {}, {"scorer/tests/Online.t.sol": test})
            result = await forge(box, timeout=FORGE_SECONDS)
            assert result.success, result.stderr + result.stdout
            assert json.loads(result.stdout)["test/Online.t.sol:OnlineTest"]["test_results"]["testPublicRpc()"]["status"] == "Success"
            await prepare_forge(box, {"src/Missing.sol": b"pragma solidity =0.8.29; contract Missing {}"}, {})
            missing = await forge(box, timeout=FORGE_SECONDS)
            assert not missing.success and "No solc version installed that matches" in missing.stderr
            after = await runner_exec(box, ["sh", "-c", "sha256sum /home/agent/.svm/*/solc-*"])
            assert after.stdout == installed.stdout
            assert "/0.8.30/solc-0.8.30" in after.stdout
        anyio.run(proof)
    finally:
        docker(*compose, "down", "--volumes", check=False)


@pytest.mark.parametrize("failure", ["crash", "json"])
def test_free_check_rejects_broken_untouched_checker(tmp_path, failure, config_path):
    folder = tmp_path / "transactions" / "broken"
    shutil.copytree(ROOT / "evals/transactions/send-six-decimal-token", folder)
    path = folder / "scorer/check.py"
    broken = "raise RuntimeError('untouched checker crashed')" if failure == "crash" else "print('invalid JSON'); raise SystemExit(0)"
    path.write_text(path.read_text().replace("sent =", f"if balance == 0:\n    {broken}\nsent ="))
    result = subprocess.run(["uv", "run", "ethevals", "check", "--evals", str(folder), "--epochs", "1",
                             "--output", str(tmp_path / "check"), "--config", str(config_path)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 1, result.stdout + result.stderr
    rows = [json.loads(line) for line in (tmp_path / "check/empty/rows.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows] == ["error"]
    references = [json.loads(line) for line in (tmp_path / "check/reference/rows.jsonl").read_text().splitlines()]
    assert [row["status"] for row in references] == ["passed"]


@pytest.mark.docker
def test_custom_compose_prepares_stock_images_for_check_and_run(tmp_path, monkeypatch):
    import shutil
    import uuid
    import subprocess
    from ethevals.sandboxes import IMAGES
    from ethevals.images.tag import image_tag
    import ethevals.preparation as preparation
    import ethevals.sandboxes as sandboxes
    images = tmp_path / "images"
    shutil.copytree(IMAGES, images)
    dockerfile = images / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text() + "\nLABEL build-proof=" + uuid.uuid4().hex + "\n")
    tag = image_tag(images)
    monkeypatch.setattr(preparation, "IMAGES", images)
    monkeypatch.setattr(sandboxes, "IMAGES", images)
    folder = tmp_path / "evals/building/custom"
    shutil.copytree(ROOT / "evals/building/erc20-points-token", folder)
    (folder / "compose.yaml").write_text("services:\n  extra:\n    image: " + tag + "\n    mem_limit: 64m\n")
    config = fixture_config()
    evaluation = load_eval(folder, config)
    for output, fresh in [(tmp_path / "pr", True), (tmp_path / "after-merge", False)]:
        success, rows = run([evaluation], config, output, answer="reference", epochs=1, fresh=fresh)
        assert (success, rows[0]["status"]) == (True, "passed")
        composed = yaml.safe_load((output / "inputs" / evaluation.hash / "compose.yaml").read_bytes())
        assert composed["services"]["scorer"]["image"] == tag
        assert all("build" not in service for service in composed["services"].values())
    subprocess.run(["docker", "image", "rm", tag], check=True, capture_output=True)
