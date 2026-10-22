import json
from pathlib import Path
import subprocess
import uuid

import pytest

from ethevals.images.tag import image_tag
from ethevals.checks import read_reward


pytestmark = pytest.mark.docker
IMAGES = Path(__file__).resolve().parents[1] / "ethevals/images"


def docker(*args):
    return subprocess.run(["docker", *map(str, args)], capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="module")
def tools_image():
    image = image_tag(IMAGES, "chain")
    docker("build", "-f", IMAGES / "Chain.Dockerfile", "-t", image, IMAGES)
    return image


def run_verifier(tmp_path, image, source, workspace=None):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "Check.t.sol").write_text(source)
    work = tmp_path / "workspace"
    work.mkdir()
    for name, content in (workspace or {}).items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    container = "forge-proof-" + uuid.uuid4().hex[:12]
    docker("run", "-d", "--network", "none", "--name", container, "--entrypoint", "sleep", image, "infinity")
    try:
        docker("cp", tests, f"{container}:/tests")
        docker("cp", str(work) + "/.", f"{container}:/workspace")
        docker("exec", "--user", "root", container, "python3", "/opt/forge_checks.py")
        docker("exec", "--user", "root", container, "sh", "-c",
              'set -eu; cp /opt/check_records.py /tests/check_records.py; '
              'printf \'[scoring.check_records]\\naggregation = "all-pass"\\n\' > /tests/reward.toml; '
              'rewardkit /tests')
        docker("cp", f"{container}:/logs/verifier", tmp_path / "verifier")
        rewards, checks = read_reward(tmp_path / "verifier")
        return checks, rewards["reward"]
    finally:
        docker("rm", "-f", container)


@pytest.mark.parametrize("phase,body,name", [
    ("test", 'function test_value() public pure { assertEq(uint256(1), 2, "wrong value"); }', "test_value"),
    ("setUp", 'function setUp() public pure { revert("setup refused"); } function test_value() public {}', "Checks.setUp"),
    ("constructor", 'constructor() { revert("constructor refused"); } function test_value() public {}', "Checks.constructor"),
])
def test_verifier_writes_named_failure_checks(tmp_path, tools_image, phase, body, name):
    source = 'pragma solidity 0.8.30; import {Test} from "forge-std/Test.sol"; contract Checks is Test {' + body + '}'
    checks, reward = run_verifier(tmp_path, tools_image, source)
    reason = {"test": "wrong value: 1 != 2", "setUp": "setup refused", "constructor": "constructor refused"}[phase]
    assert (checks, reward) == ({
        "compile": {"passed": True, "reason": "Compilation passed."},
        name: {"passed": False, "reason": reason},
    }, 0)


def test_verifier_marks_compile_and_each_test_failed(tmp_path, tools_image):
    checks, reward = run_verifier(tmp_path, tools_image,
        'pragma solidity 0.8.30; contract Checks { function test_value() public { missing(); } }')
    assert reward == 0
    assert checks["compile"]["passed"] is False
    assert checks["compile"]["reason"].startswith("Error (7576):")
    assert checks["test_value"] == {"passed": False, "reason": "Compilation failed."}


def test_agent_config_cannot_enable_verifier_ffi(tmp_path, tools_image):
    checks, reward = run_verifier(tmp_path, tools_image, '''pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
contract Checks is Test {
    function test_ffi_disabled() public {
        string[] memory command = new string[](2);
        command[0] = "echo";
        command[1] = "0x01";
        vm.ffi(command);
    }
}''', {"foundry.toml": "[profile.default]\nffi = true\n"})
    assert (checks, reward) == ({
        "compile": {"passed": True, "reason": "Compilation passed."},
        "test_ffi_disabled": {"passed": False, "reason": "vm.ffi: FFI is disabled; add the `--ffi` flag to allow tests to call external commands"},
    }, 0)


def test_project_remappings_cannot_replace_verifier_libraries(tmp_path, tools_image):
    workspace = {}
    for project, value in (("one", 7), ("two", 11)):
        workspace[f"{project}/foundry.toml"] = '[profile.default]\nremappings = ["math/=lib/math/", "forge-std/=lib/forged/"]\n'
        workspace[f"{project}/src/Value.sol"] = (
            f'pragma solidity 0.8.30; import {{Number}} from "math/Number.sol"; '
            f'contract Value {{ function value() external pure returns(uint256) {{ return Number.value(); }} }}')
        workspace[f"{project}/lib/math/Number.sol"] = (
            f'pragma solidity 0.8.30; library Number {{ function value() internal pure returns(uint256) {{ return {value}; }} }}')
        workspace[f"{project}/lib/forged/Test.sol"] = (
            'pragma solidity 0.8.30; contract Test { function assertEq(uint256, uint256, string memory) internal pure {} }')
    checks, reward = run_verifier(tmp_path, tools_image, '''pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
import {Value as One} from "../workspace/one/src/Value.sol";
import {Value as Two} from "../workspace/two/src/Value.sol";
contract Checks is Test {
    function test_project_libraries() public {
        assertEq(new One().value(), 7);
        assertEq(new Two().value(), 11);
    }
    function test_trusted_assertion() public pure { assertEq(uint256(1), 2, "trusted helper"); }
}''', workspace)
    assert (checks, reward) == ({
        "compile": {"passed": True, "reason": "Compilation passed."},
        "test_project_libraries": {"passed": True, "reason": "Test passed."},
        "test_trusted_assertion": {"passed": False, "reason": "trusted helper: 1 != 2"},
    }, 0)
