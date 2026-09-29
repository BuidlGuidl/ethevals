"""Submission boundaries, attempt limits, and grader evidence."""
import json
import shutil
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from inspect_ai.solver import generate, solver

from ethevals.checks import CHECK_SOLVERS, CheckRun
from support import load_config
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from support import run
from ethevals.sandboxes import IMAGES, validate_compose
from ethevals.scorers import forge_checks
from support import build_task

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"
CHECK = "forge:test/Token.t.sol:TokenTest:testSupply()"
PASS = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
    "testSupply()": {"status": "Success"}}}})


@pytest.mark.parametrize("value", ["$SECRET_PROBE", "${SECRET_PROBE}", "$$literal/$SECRET_PROBE"])
def test_compose_rejects_both_interpolation_forms(tmp_path, value):
    data = yaml.safe_load((IMAGES / "stock.compose.yaml").read_text())
    data["services"]["default"].pop("build")
    data["services"]["default"]["environment"] = {"LEAK": value}
    path = tmp_path / "compose.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="host environment substitution"):
        validate_compose(path)


def test_compose_checks_decoded_values_and_allows_literal_dollars(tmp_path):
    text = (IMAGES / "stock.compose.yaml").read_text().replace("    build: .\n", "")
    text = text.replace("    init: true", '    environment: {VALUE: "\\u0024SECRET_PROBE"}\n    init: true', 1)
    path = tmp_path / "compose.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match="host environment substitution"):
        validate_compose(path)
    path.write_text(text.replace('\\u0024SECRET_PROBE', '$$SECRET_PROBE'))
    validate_compose(path)
    assert load_eval(BUILD, load_config()).id == "building/erc20-points-token"


@pytest.mark.parametrize("name", ["scorer/tests/cache", "workspace/cache", "workspace/lib/cache"])
def test_reserved_symlinks_are_rejected_before_read(tmp_path, name):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(tmp_path / "host-secret")
    with pytest.raises(ValueError, match="symlinks"):
        load_eval(folder, load_config())


def test_reserved_scorer_directory_is_rejected(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    path = folder / "scorer/tests/lib/Extra.t.sol"
    path.parent.mkdir()
    path.write_text("contract Extra { function testFree() public {} }")
    with pytest.raises(ValueError, match="reserved names"):
        load_eval(folder, load_config())


def test_eval_root_cannot_be_a_symlink(tmp_path):
    folder = tmp_path / "building/alias"
    folder.parent.mkdir()
    folder.symlink_to(BUILD, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        load_eval(folder, load_config())


@pytest.mark.parametrize("diagnostic", [
    "Error: Encountered invalid solc version =0.8.99. No solc version exists that matches.",
    "CompilerError: Stack too deep. Try compiling with --via-ir.",
])
def test_submission_compile_errors_record_one_check(diagnostic):
    reason = diagnostic + (" Scoring is offline. Available solc versions: 0.8.30." if "solc version" in diagnostic else "")
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


def test_errors_stop_after_two_attempts(tmp_path, monkeypatch):
    @solver
    def crash():
        async def solve(state, generate):
            raise RuntimeError("Container transport failed.")
        return solve

    monkeypatch.setitem(CHECK_SOLVERS, "quiz", lambda evaluation, answer: CheckRun(crash()))
    config = load_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    output = tmp_path / "results"
    for attempt, expected_success in [(1, False), (2, False), (2, True)]:
        success, rows = run([evaluation], config, output, answer="reference", epochs=1)
        assert success is expected_success
        assert (rows[0]["status"], rows[0]["attempt"]) == ("error", attempt)
    assert len(list((output / "logs").glob("*.eval"))) == 2
    success, rows = run([evaluation], config, output, answer="reference", epochs=1, retry_errors=True)
    assert (success, rows[0]["status"], rows[0]["attempt"]) == (False, "error", 3)
    assert rows[0]["checks"] == {}
    success, rows = run([evaluation], config, output, answer="reference", epochs=1)
    assert (success, rows[0]["attempt"]) == (True, 3)


@pytest.mark.parametrize("budget", [5.0, 0.01])
def test_cost_limit_discounts_cache_for_a_forty_call_build(tmp_path, budget):
    config = load_config()
    config.cost_limit = budget
    config.agents["opus"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    task = build_task(evaluation, config, "opus", "vanilla", None, 1)

    @solver
    def forty_calls():
        async def solve(state, generate):
            for _ in range(40):
                state = await generate(state)
            return state
        return solve

    def reply(messages, tools, tool_choice, config):
        output = ModelOutput.from_content("mockllm/model", "8004")
        output.usage = ModelUsage(input_tokens=1000, input_tokens_cache_read=19000, output_tokens=1000, total_tokens=21000)
        return output

    task.solver = forty_calls()
    task.model = get_model("mockllm/model", custom_outputs=reply)
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    assert (row["status"], row["total_tokens"]) == (("passed", 840000) if budget == 5.0 else ("failed", 21000))
    assert row["model_cost_usd"] == pytest.approx(1.58 if budget == 5.0 else 0.0395)
    assert row["grader_cost_usd"] == 0


def test_unknown_harness_fails_at_config_load(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(load_config().model_dump()).replace("harness: claude_code", "harness: absent"))
    with pytest.raises(ValueError, match="unknown harness 'absent'"):
        load_config(path)


def test_loaded_eval_uses_captured_files(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    config = load_config()
    evaluation = load_eval(folder, config)
    (folder / "workspace/src/BuilderPoints.sol").write_text("modified after loading")
    (folder / "scorer/rubric.md").write_text("## replaced\nWrong question")
    task = build_task(evaluation, config, None, "internet", "reference", 1)
    from ethevals.files import inline_file
    assert task.dataset[0].files["/workspace/src/BuilderPoints.sol"] == inline_file((BUILD / "workspace/src/BuilderPoints.sol").read_bytes())
    assert evaluation.files["scorer/rubric.md"] == (BUILD / "scorer/rubric.md").read_bytes()
    assert load_eval(folder, config).hash != evaluation.hash
