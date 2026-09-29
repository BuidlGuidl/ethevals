from pathlib import Path
import json

from ethevals.scorers import forge_checks, prepare_forge
from ethevals.scoring_base import SubmissionFailed
from inspect_ai.util import ExecResult
import anyio
import pytest


FORGE_OUTPUT = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
    "testSupply()": {"status": "Success", "reason": None},
    "testTransfer()": {"status": "Failure", "reason": "Wrong recipient balance\nexpected 10"},
}}})
CAPTURES = json.loads((Path(__file__).parent / "fixtures/forge-1.5.1.json").read_text())


def test_forge_names_and_reasons():
    assert forge_checks(FORGE_OUTPUT, "", 1) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        "forge:test/Token.t.sol:TokenTest:testSupply()": {"passed": True, "reason": "Test passed."},
        "forge:test/Token.t.sol:TokenTest:testTransfer()": {"passed": False, "reason": "Wrong recipient balance expected 10"},
    }


@pytest.mark.parametrize("captured", [CAPTURES[name] for name in ("syntax", "version", "missing_method")] + [
    {"stdout": "", "stderr": "CompilerError: Stack too deep", "returncode": 1}])
def test_compiler_error_is_a_failed_check(captured):
    assert forge_checks(**captured)["forge:compile"]["passed"] is False


def test_non_utf8_source_is_a_failed_submission():
    class Box:
        async def exec(self, *args, **kwargs):
            return ExecResult(success=True, returncode=0, stdout="", stderr="")
    with pytest.raises(SubmissionFailed, match="not valid UTF-8"):
        anyio.run(prepare_forge, Box(), {"src/X.sol": b"\xff"}, {})


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
