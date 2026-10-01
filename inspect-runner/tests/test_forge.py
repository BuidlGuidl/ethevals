from pathlib import Path
import json

from ethevals.scorers import forge_checks
import pytest


FORGE_OUTPUT = json.dumps({"scorer/tests/Token.t.sol:TokenTest": {"test_results": {
    "testSupply()": {"status": "Success", "reason": None},
    "testTransfer()": {"status": "Failure", "reason": "Wrong recipient balance\nexpected 10"},
}}})
CAPTURES = json.loads((Path(__file__).parent / "fixtures/forge-1.5.1.json").read_text())


def test_forge_names_and_reasons():
    assert forge_checks(FORGE_OUTPUT, "", 1) == (True, "Compilation passed.", {
        "testSupply": {"passed": True, "reason": "Test passed."},
        "testTransfer": {"passed": False, "reason": "Wrong recipient balance expected 10"},
    })


@pytest.mark.parametrize("captured", [CAPTURES[name] for name in ("syntax", "missing_method")] + [
    {"stdout": "", "stderr": "CompilerError: Stack too deep", "returncode": 1}])
def test_compiler_error_is_a_failed_check(captured):
    assert forge_checks(**captured)[0] is False


def test_captured_constructor_failure_names_the_contract():
    assert forge_checks(**CAPTURES["constructor"]) == (True, "Compilation passed.", {
        "Tests.constructor": {"passed": False, "reason": "bad submission"},
    })


def test_unsatisfiable_pragma_is_a_failed_compile():
    assert forge_checks(**CAPTURES["version"]) == (False,
        "Error: Encountered invalid solc version in src/A.sol: No solc version exists that matches the version requirement: ^0.9.0", {})


def test_setup_failure_names_the_contract():
    output = json.dumps({"scorer/tests/Token.t.sol:TokenTest": {"test_results": {
        "setUp()": {"status": "Failure", "reason": "constructor failed"}}}})
    assert forge_checks(output, "", 1) == (True, "Compilation passed.", {
        "TokenTest.setUp": {"passed": False, "reason": "constructor failed"},
    })


def test_inherited_checks_cannot_overwrite_each_other():
    output = json.dumps({suite: {"test_results": {"test_shared()": {"status": "Success"}}}
                         for suite in ("scorer/tests/Base.t.sol:First", "scorer/tests/Base.t.sol:Second")})
    with pytest.raises(RuntimeError, match="Duplicate Forge check 'test_shared'.*First.*Second"):
        forge_checks(output, "", 0)


def test_compiler_download_failure_is_an_error():
    stderr = "Error: error decoding response body\n\nContext:\n- Error #0: request or response body error\n- Error #1: operation timed out\n"
    with pytest.raises(RuntimeError, match="error decoding response body"):
        forge_checks("", stderr, 1)


@pytest.mark.parametrize("code,stdout,stderr,reason", [
    (1, "", "thread panicked", "without test results"),
    (1, '{"truncated":', "Error: Compilation failed", "without test results"),
    (137, CAPTURES["reference"]["stdout"], "", "terminated"),
])
def test_unexplained_forge_failure_is_an_error(code, stdout, stderr, reason):
    with pytest.raises(RuntimeError, match=reason):
        forge_checks(stdout, stderr, code)
