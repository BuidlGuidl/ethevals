from pathlib import Path
import json

from ethevals.scorers import forge_checks
import pytest


FORGE_OUTPUT = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
    "testSupply()": {"status": "Success", "reason": None},
    "testTransfer()": {"status": "Failure", "reason": "Wrong recipient balance\nexpected 10"},
}}})
CHECK = "forge:test/Token.t.sol:TokenTest:testSupply()"
PASS = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
    "testSupply()": {"status": "Success"}}}})
CAPTURES = json.loads((Path(__file__).parent / "fixtures/forge-1.5.1.json").read_text())


def test_forge_names_and_reasons():
    assert forge_checks(FORGE_OUTPUT, "", 1) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        "forge:test/Token.t.sol:TokenTest:testSupply()": {"passed": True, "reason": "Test passed."},
        "forge:test/Token.t.sol:TokenTest:testTransfer()": {"passed": False, "reason": "Wrong recipient balance expected 10"},
    }


def test_compiler_error_is_a_failed_check():
    captured = json.loads((Path(__file__).parent / "fixtures/forge-1.5.1.json").read_text())["syntax"]
    assert forge_checks(**captured) == {
        "forge:compile": {"passed": False, "reason": "Error (6933): Expected primary expression."},
    }


@pytest.mark.parametrize("diagnostic", [
    "Error: Encountered invalid solc version =0.8.99. No solc version exists that matches.",
    "CompilerError: Stack too deep. Try compiling with --via-ir.",
])
def test_submission_compile_errors_record_one_check(diagnostic):
    reason = diagnostic + (" Available solc versions: 0.8.30." if "solc version" in diagnostic else "")
    assert forge_checks("", diagnostic, 1) == {
        "forge:compile": {"passed": False, "reason": reason},
    }


def test_pass_compile_and_setup_failure_record_observed_checks():
    setup = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
        "setUp()": {"status": "Failure", "reason": "EvmError: Revert"}}}})
    assert forge_checks(PASS, "", 0) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        CHECK: {"passed": True, "reason": "Test passed."}}
    assert forge_checks("", "CompilerError: Stack too deep", 1) == {
        "forge:compile": {"passed": False, "reason": "CompilerError: Stack too deep"}}
    assert forge_checks(setup, "", 1) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        "forge:test/Token.t.sol:TokenTest:setUp()": {"passed": False, "reason": "EvmError: Revert"}}


def test_captured_constructor_failure_keeps_forge_check_name():
    assert forge_checks(**CAPTURES["constructor"]) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        "forge:test/Token.t.sol:Tests:constructor()": {"passed": False, "reason": "bad submission"},
    }


@pytest.mark.parametrize("code,stdout,stderr,reason", [
    (1, "", "thread panicked", "without test results"),
    (1, '{"truncated":', "Error: Compilation failed", "without test results"),
    (137, CAPTURES["reference"]["stdout"], "", "terminated"),
])
def test_unexplained_forge_failure_is_an_error(code, stdout, stderr, reason):
    with pytest.raises(RuntimeError, match=reason):
        forge_checks(stdout, stderr, code)
