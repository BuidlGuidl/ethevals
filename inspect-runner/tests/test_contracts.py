"""Scoring contracts exercised through Inspect and the results exporter."""
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from inspect_ai.solver import generate
from inspect_ai.util import ExecResult, OutputLimitExceededError

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose, prepare_eval
from ethevals.rows import results_rows
from ethevals.sandboxes import IMAGES, validate_compose
from ethevals.scorers import rubric_budget, rubric_evidence, rubric_reply
from support import build_task

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"
CHECK = "forge:test/Token.t.sol:TokenTest:testSupply()"
NAMES = {"forge:compile", CHECK, "rubric:uses_openzeppelin", "rubric:protects_holders"}
PASS = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {"testSupply()": {"status": "Success"}}}})


@pytest.fixture
def scoring_case(tmp_path, monkeypatch):
    import ethevals.scorers as scorers
    config = load_config()
    config.models["opus"].model = "mockllm/player"
    config.grader.model = "mockllm/grader"
    evaluation = load_eval(BUILD, config)
    task = build_task(evaluation, config, "opus", "internet", None, 1)
    task.dataset[0].sandbox = task.dataset[0].files = None
    task.solver = generate()
    source = {"src/Token.sol": b"contract Token {}"}
    case = {"snapshots": 0, "source": source, "compiled": source, "forge_error": None, "requests": []}

    async def submitted():
        case["snapshots"] += 1
        return case["source"]

    async def prepare(*args):
        pass

    async def forge(*args):
        if case["forge_error"]:
            raise case["forge_error"]
        return ExecResult(success=True, returncode=0, stdout=PASS, stderr="")

    async def compiled(*args):
        return case["compiled"]

    monkeypatch.setattr(scorers, "workspace_files", submitted)
    monkeypatch.setattr(scorers, "sandbox", lambda name: object())
    monkeypatch.setattr(scorers, "prepare_forge", prepare)
    monkeypatch.setattr(scorers, "forge", forge)
    monkeypatch.setattr(scorers, "compiled_sources", compiled)

    def execute(replies, budget=None):
        if budget is not None:
            task.dataset[0].metadata["grader_cost_limit_usd"] = budget
        pending = iter(replies)

        def grade(messages, tools, tool_choice, config):
            case["requests"].append(messages)
            reply = next(pending)
            if isinstance(reply, Exception):
                raise reply
            output = ModelOutput.from_content("mockllm/grader", reply)
            output.usage = ModelUsage(input_tokens=100, output_tokens=100, total_tokens=200)
            return output

        log = eval(task, model_roles={"grader": get_model("mockllm/grader", custom_outputs=grade)},
                   log_dir=str(tmp_path / "logs"), display="none")[0]
        case["log"] = log
        return results_rows(log)[0]

    case["run"] = execute
    return case


YES = '{"passed": true, "reason": "Uses standard transfers."}'
NO = '{"passed": false, "reason": "Owner can seize tokens."}'


def test_grader_provider_failure_is_an_error_and_keeps_prior_verdict(scoring_case):
    row = scoring_case["run"]([YES, RuntimeError("Provider unavailable: 503")])
    assert (row["status"], row["passed"]) == ("error", None)
    assert set(row["checks"]) == NAMES
    assert row["checks"]["rubric:uses_openzeppelin"] == {"passed": True, "reason": "Uses standard transfers."}
    assert "503" in row["error_reason"]


def test_grader_no_is_a_failed_check(scoring_case):
    row = scoring_case["run"]([YES, NO])
    assert row["status"] == "failed"
    assert row["checks"]["rubric:protects_holders"] == {"passed": False, "reason": "Owner can seize tokens."}
    assert row["grader_tokens"] == 400


def test_invalid_grader_replies_are_a_bounded_error(scoring_case):
    row = scoring_case["run"](["No JSON.", "Still no JSON."])
    assert (row["status"], row["grader_tokens"]) == ("error", 400)
    assert "after two calls" in row["error_reason"]
    assert set(row["checks"]) == NAMES


def test_grader_budget_error_keeps_finished_verdict(scoring_case):
    row = scoring_case["run"]([YES, YES], budget=0.004)
    assert (row["status"], row["limit"]) == ("error", None)
    assert "Grader cost limit reached." in row["error_reason"]
    assert row["checks"]["rubric:uses_openzeppelin"] == {"passed": True, "reason": "Uses standard transfers."}


def test_submission_output_limit_fills_all_checks(scoring_case):
    scoring_case["forge_error"] = OutputLimitExceededError("10 MiB", "truncated")
    row = scoring_case["run"]([])
    assert (row["status"], row["grader_tokens"]) == ("failed", 0)
    assert row["checks"] == {name: {"passed": False, "reason": "Submission exceeded Forge's time or output limit: The sandbox output stream limit of 10 MiB was exceeded."} for name in NAMES}


def test_one_snapshot_supplies_tests_and_grader(scoring_case):
    row = scoring_case["run"]([YES, YES])
    assert row["status"] == "passed"
    assert scoring_case["snapshots"] == 1
    assert "contract Token {}" in "\n".join(message.text for message in scoring_case["requests"][0])


def test_incomplete_evidence_keeps_the_graders_verdict(scoring_case):
    scoring_case["compiled"] = {"src/Token.sol": b"contract Token {}", "lib/large/Huge.sol": b"x" * 100001}
    row = scoring_case["run"]([YES, YES])
    assert row["status"] == "passed"
    assert row["checks"]["rubric:protects_holders"] == {"passed": True, "reason": "Uses standard transfers."}
    assert "lib/large/Huge.sol" in "\n".join(message.text for message in scoring_case["requests"][0])


@pytest.mark.parametrize("text", ['The token extends {ERC20}. ' + YES, '{"verdict": ' + YES + '}', '```json\n' + YES + '\n```'])
def test_verdict_parser_finds_expected_keys(text):
    assert rubric_reply(text) == {"passed": True, "reason": "Uses standard transfers."}


def test_evidence_gives_src_priority_at_the_cap():
    files = {f"lib/vendor/{n}.sol": b"v" * 100000 for n in range(3)}
    files["src/Token.sol"] = b"contract Token {}"
    evidence, omitted = rubric_evidence(files)
    assert list(evidence) == ["src/Token.sol", "lib/vendor/0.sol", "lib/vendor/1.sol"]
    assert omitted == ["lib/vendor/2.sol"]


def test_grader_budget_covers_full_evidence_for_each_question():
    config = load_config()
    evaluation = load_eval(BUILD, config)
    first = rubric_budget(evaluation, config)
    files = {**evaluation.files, "scorer/rubric.md": b"## one\nQuestion?\n## two\nQuestion?\n## three\nQuestion?"}
    larger = rubric_budget(replace(evaluation, files=files), config)
    assert first > 2 * 2 * (300000 * 6.25 + 4096 * 25) / 1_000_000
    assert larger > first


def test_compose_rejects_binary_yaml(tmp_path):
    document = yaml.safe_load((IMAGES / "stock.compose.yaml").read_bytes())
    document["services"]["default"].pop("build")
    document["services"]["default"]["environment"] = {"TOKEN": b"$SECRET_PROBE"}
    with pytest.raises(ValueError, match="unsupported YAML scalar"):
        validate_compose(tmp_path / "compose.yaml", data=yaml.safe_dump(document).encode())


def test_compose_runs_the_normalized_captured_document(tmp_path):
    config = load_config()
    evaluation = load_eval(BUILD, config)
    raw = (IMAGES / "stock.compose.yaml").read_bytes().replace(b"    build: .\n", b"") + b"# author bytes\n"
    evaluation = replace(evaluation, files={**evaluation.files, "compose.yaml": raw})
    path = prepare_compose(evaluation, tmp_path)
    assert path.read_bytes() == yaml.safe_dump(yaml.safe_load(raw), sort_keys=True).encode()
    assert path.read_bytes() != raw


def test_quiz_internet_has_no_foundry_files_or_note():
    config = load_config()
    evaluation = load_eval(ROOT / "evals/concepts/wei-per-ether", config)
    task = build_task(evaluation, config, None, "internet", "reference", 1)
    assert task.dataset[0].input == "How many wei equal one ether?"
    assert task.dataset[0].files == {"/workspace/.gitkeep": "data:application/octet-stream;base64,"}
    assert task.dataset[0].sandbox.type == "docker"


def test_author_foundry_file_is_rejected(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    (folder / "workspace/foundry.toml").write_text("[profile.default]\nffi=true\n")
    with pytest.raises(ValueError, match="runner-owned"):
        load_eval(folder, load_config())


def test_hard_link_is_rejected(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    outside = tmp_path / "outside.txt"
    outside.write_text("inert sentinel")
    os.link(outside, folder / "workspace/probe.txt")
    with pytest.raises(ValueError, match="hard links"):
        load_eval(folder, load_config())


def test_finder_junk_under_scorer_does_not_change_hash(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    config = load_config()
    before = load_eval(folder, config)
    (folder / "scorer/.DS_Store").write_bytes(b"Finder metadata")
    after = load_eval(folder, config)
    assert after.id == "building/token"
    assert after.hash == before.hash


def test_compose_directory_reports_a_load_error(tmp_path):
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    (folder / "compose.yaml").mkdir()
    with pytest.raises(ValueError, match="must be a regular file"):
        load_eval(folder, load_config())


def test_logs_only_record_eval_identity_in_scorer_options(scoring_case):
    row = scoring_case["run"]([YES, YES])
    options = scoring_case["log"].eval.scorers[0].options
    assert options == {"eval_id": "building/erc20-points-token", "eval_hash": row["eval_hash"]}
    assert row["status"] == "passed"


def test_cached_check_names_are_known_before_an_error_epoch(tmp_path, monkeypatch):
    import ethevals.preparation as preparation
    config = load_config()
    evaluation = load_eval(BUILD, config)
    path = tmp_path / "inputs" / evaluation.hash / "checks.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([CHECK]))
    monkeypatch.setattr(preparation, "CHECK_SETS", {})
    prepared = prepare_eval(evaluation, tmp_path)
    assert prepared.test_checks == ("forge:test/Token.t.sol:TokenTest:testSupply()",)
    # A second output uses the already discovered contract, without Docker.
    second = prepare_eval(evaluation, tmp_path / "second")
    assert second.test_checks == ("forge:test/Token.t.sol:TokenTest:testSupply()",)
    assert json.loads((tmp_path / "second/inputs" / evaluation.hash / "checks.json").read_text()) == [CHECK]
