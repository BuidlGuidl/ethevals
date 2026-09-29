from pathlib import Path

from ethevals.loader import load_eval
import pytest

from support import fixture_config



@pytest.mark.parametrize("output", [None, [], {}, {"files": [],}, {"files": {}, "extra": 1},
    {"files": {"/absolute": "x"}}, {"files": {"../parent": "x"}}, {"files": {"a/../b": "x"}},
    {"files": {"a//b": "x"}}, {"files": {".": "x"}}, {"files": {"": "x"}},
    {"files": {"value": 1}}, {"files": {3: "x"}}, {"files": {"README.md": "replacement"}}])
def test_setup_rejects_invalid_output(output):
    from ethevals.check_script import setup_files
    with pytest.raises(ValueError, match="Setup script"):
        setup_files(output, {"workspace/README.md": b"original"})


def test_setup_accepts_selected_nested_files():
    from ethevals.check_script import setup_files
    assert setup_files({"files": {"data/key.json": "key", "chain.json": "chain"}}, {}) == {
        "data/key.json": "key", "chain.json": "chain"}


@pytest.mark.parametrize("name", ["check", "check.sh", "check.py"])
def test_runnable_check_names_load_and_stay_private(tmp_path, name):
    import shutil
    root = Path(__file__).resolve().parents[2]
    folder = tmp_path / "transactions" / "act"
    shutil.copytree(root / "evals/transactions/send-six-decimal-token", folder)
    (folder / "scorer/check.py").rename(folder / "scorer" / name)
    evaluation = load_eval(folder, fixture_config())
    assert evaluation.files["scorer/" + name].startswith(b"#!/usr/bin/env python3")
    assert set(evaluation.sample().files) == {"/workspace/README.md"}
    (folder / "scorer/check.extra").write_text("#!/bin/sh\nexit 1\n")
    with pytest.raises(ValueError, match="Expected one scorer/check"):
        load_eval(folder, fixture_config())


@pytest.mark.parametrize("value", [None, [], {}, {"Bad": {"passed": True, "reason": "yes"}},
    {1: {"passed": True, "reason": "yes"}}, {"ok": None}, {"ok": {"passed": 1, "reason": "yes"}},
    {"ok": {"passed": True, "reason": " "}}, {"ok": {"passed": True, "reason": 1}},
    {"ok": {"passed": True}}, {"ok": {"passed": True, "reason": "yes", "extra": 1}}])
def test_check_script_rejects_invalid_checks(value):
    from ethevals.check_script import script_checks
    with pytest.raises(ValueError, match="Check script"):
        script_checks(value)


def test_check_script_normalizes_reasons():
    from ethevals.check_script import script_checks
    assert script_checks({"balance": {"passed": False, "reason": " Balance\n is zero. "}}) == {
        "script:balance": {"passed": False, "reason": "Balance is zero."}}


def test_act_requires_check_script_and_allows_declared_chain_file(tmp_path):
    import shutil
    root = Path(__file__).resolve().parents[2]
    folder = tmp_path / "transactions" / "act"
    shutil.copytree(root / "evals/transactions/send-six-decimal-token", folder)
    (folder / "workspace/chain.json").write_text("declared input")
    assert load_eval(folder, fixture_config()).files["workspace/chain.json"] == b"declared input"
    (folder / "scorer/tests").mkdir()
    (folder / "scorer/tests/Test.t.sol").write_text("contract Test {}")
    with pytest.raises(ValueError, match="scorer files do not match type act"):
        load_eval(folder, fixture_config())


def test_script_failure_includes_stderr_tail():
    import anyio
    from inspect_ai.util import ExecResult
    from ethevals.check_script import script_result

    class Box:
        async def exec(self, command, **kwargs):
            return ExecResult(success=False, returncode=1, stdout="",
                              stderr="x" * 6000 + "\nValueError: bad setup amount")

    with pytest.raises(RuntimeError, match="ValueError: bad setup amount") as error:
        anyio.run(script_result, "scorer/setup.py", Box())
    assert len(str(error.value)) < 4200
