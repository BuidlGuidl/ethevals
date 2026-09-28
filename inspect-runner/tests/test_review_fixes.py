"""Regression cases from the step 2b review."""
import json
import shutil
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from inspect_ai.solver import generate, solver

from ethevals.checks import CHECK_SOLVERS, CheckRun
from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from support import run
from ethevals.sandboxes import IMAGES, validate_compose
from ethevals.scorers import forge_checks, rubric_evidence
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
def test_submission_compile_errors_fill_the_fixed_check_set(diagnostic):
    reason = diagnostic + " Scoring is offline. Available solc versions: 0.8.30."
    assert forge_checks("", diagnostic, 1, [CHECK]) == {
        "forge:compile": {"passed": False, "reason": reason},
        CHECK: {"passed": False, "reason": reason},
    }


def test_pass_compile_and_setup_failure_have_the_same_checks():
    setup = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
        "setUp()": {"status": "Failure", "reason": "EvmError: Revert"}}}})
    assert forge_checks(PASS, "", 0, [CHECK]) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        CHECK: {"passed": True, "reason": "Test passed."}}
    assert forge_checks("", "CompilerError: Stack too deep", 1, [CHECK]) == {
        "forge:compile": {"passed": False, "reason": "CompilerError: Stack too deep Scoring is offline. Available solc versions: 0.8.30."},
        CHECK: {"passed": False, "reason": "CompilerError: Stack too deep Scoring is offline. Available solc versions: 0.8.30."}}
    assert forge_checks(setup, "", 1, [CHECK]) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        CHECK: {"passed": False, "reason": "EvmError: Revert"}}


def test_agent_test_functions_do_not_become_checks():
    output = json.loads(PASS)
    output["src/Token.sol:Extra"] = {"test_results": {"testFree()": {"status": "Success"}}}
    assert forge_checks(json.dumps(output), "", 0, [CHECK]) == {
        "forge:compile": {"passed": True, "reason": "Compilation passed."},
        CHECK: {"passed": True, "reason": "Test passed."}}


def test_rubric_reports_omitted_dependency_files():
    assert rubric_evidence({"lib/custom/Huge.sol": b"x" * 100001, "src/Token.sol": b"contract Token {}"}) == (
        {"src/Token.sol": "contract Token {}"}, ["lib/custom/Huge.sol"])


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
    for attempt in [1, 2, 2]:
        success, rows = run([evaluation], config, output, answer="reference", epochs=1)
        assert success is False
        assert (rows[0]["status"], rows[0]["attempt"]) == ("error", attempt)
    assert len(list((output / "logs").glob("*.eval"))) == 2
    success, rows = run([evaluation], config, output, answer="reference", epochs=1, retry_errors=True)
    assert (success, rows[0]["status"], rows[0]["attempt"]) == (False, "error", 3)
    assert set(rows[0]["checks"]) == {"erc_number"}
    success, rows = run([evaluation], config, output, answer="reference", epochs=1)
    assert (success, rows[0]["attempt"]) == (False, 3)


@pytest.mark.parametrize("budget", [5.0, 0.01])
def test_cost_limit_discounts_cache_for_a_forty_call_build(tmp_path, budget):
    config = load_config()
    config.cost_limit = budget
    config.models["opus"].model = "mockllm/model"
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
    assert (row["status"], row["model_tokens"]) == (("passed", 840000) if budget == 5.0 else ("failed", 21000))
    assert row["model_metered_usd"] == pytest.approx(1.58 if budget == 5.0 else 0.0395)
    assert row["grader_metered_usd"] == 0


def test_unknown_harness_fails_at_config_load(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text((ROOT / "inspect-runner/ethevals/config.yaml").read_text().replace("harness: claude_code", "harness: absent"))
    with pytest.raises(ValueError, match="unknown harness 'absent'"):
        load_config(path)


def test_workspace_failure_fills_all_eval_checks(tmp_path, monkeypatch):
    import ethevals.scorers as scorers
    config = load_config()
    config.models["opus"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    task = build_task(load_eval(BUILD, config), config, "opus", "internet", None, 1)
    task.dataset[0].sandbox = task.dataset[0].files = None
    task.solver = generate()

    async def broken_workspace():
        raise ValueError("Workspace contains a link or special file: src/Token.sol")

    monkeypatch.setattr(scorers, "workspace_files", broken_workspace)
    row = results_rows(eval(task, log_dir=str(tmp_path / "logs"), display="none")[0])[0]
    failure = {"passed": False, "reason": "Workspace snapshot failed: Workspace contains a link or special file: src/Token.sol"}
    assert row["checks"] == {"forge:compile": failure, CHECK: failure,
                             "rubric:uses_openzeppelin": failure, "rubric:protects_holders": failure}
    assert (row["status"], row["grader_tokens"]) == ("failed", 0)


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
