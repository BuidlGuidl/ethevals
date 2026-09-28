import io
import json
import tarfile
import shutil
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.solver import generate
from inspect_ai.util import ExecResult

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.rows import results_rows
from ethevals.runner import build_task
from ethevals.sandboxes import IMAGES, unpack_workspace, validate_compose
from ethevals.scorers import forge_checks, rubric_reply

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"
FORGE_OUTPUT = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
    "testSupply()": {"status": "Success", "reason": None},
    "testTransfer()": {"status": "Failure", "reason": "Wrong recipient balance\nexpected 10"},
}}})


def test_forge_names_and_reasons():
    assert forge_checks(FORGE_OUTPUT, "", 1) == {
        "forge:test/Token.t.sol:TokenTest:testSupply()": {"passed": True, "reason": "Test passed."},
        "forge:test/Token.t.sol:TokenTest:testTransfer()": {"passed": False, "reason": "Wrong recipient balance expected 10"},
    }


def test_compiler_error_is_a_failed_check():
    assert forge_checks("", 'Error: Compiler run failed:\nError (2314): Expected semicolon.\n --> src/Token.sol:4:1', 1) == {
        "forge:compile": {"passed": False, "reason": "Error (2314): Expected semicolon."},
    }
    with pytest.raises(RuntimeError, match="Could not resolve host"):
        forge_checks("", "Could not resolve host: binaries.soliditylang.org", 1)


def test_rubric_boolean_and_reason():
    assert rubric_reply('{"passed": false, "reason": "Owner can seize tokens.\\nSee take()."}') == {
        "passed": False, "reason": "Owner can seize tokens. See take().",
    }
    with pytest.raises(ValueError, match="boolean"):
        rubric_reply('{"passed": "yes", "reason": "Fine"}')


def test_agent_sample_contains_only_workspace_files():
    config = load_config()
    config.models["opus"].model = "mockllm/model"
    task = build_task(load_eval(BUILD, config), config, "opus", "internet", None, 1)
    sample = task.dataset[0]
    assert sample.files == {
        "/workspace/foundry.toml": str(BUILD / "workspace/foundry.toml"),
        "/workspace/src/BuilderPoints.sol": str(BUILD / "workspace/src/BuilderPoints.sol"),
    }
    assert (sample.sandbox.type, Path(sample.sandbox.config).name) == ("docker", "build.compose.yaml")


@pytest.mark.parametrize("extra,reason", [
    ({"privileged": True}, "privileged"),
    ({"volumes": ["/tmp:/host"]}, "volumes are forbidden"),
    ({"volumes": [{"type": "bind", "source": "/tmp", "target": "/host"}]}, "volumes are forbidden"),
    ({"network_mode": "host"}, "forbidden options"),
    ({"build": "."}, "forbidden options"),
    ({"environment": {"KEY": None}}, "inherited host environment"),
])
def test_unsafe_compose_is_rejected(tmp_path, extra, reason):
    data = yaml.safe_load((IMAGES / "build.compose.yaml").read_text())
    data["services"]["default"].pop("build")
    path = tmp_path / "compose.yaml"
    path.write_text(yaml.safe_dump(data))
    validate_compose(path)
    data["services"]["default"].update(extra)
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match=reason):
        validate_compose(path)


def test_services_cannot_join_internet(tmp_path):
    data = yaml.safe_load((IMAGES / "build.compose.yaml").read_text())
    data["services"]["default"].pop("build")
    data["services"]["chain"] = {"image": "chain:test", "networks": ["private", "internet"]}
    path = tmp_path / "compose.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="only default and scorer can join internet"):
        validate_compose(path)


@pytest.mark.parametrize("name,link", [("../scorer/secret", False), ("src/Escape.sol", True)])
def test_workspace_archive_rejects_escape(name, link):
    def archive(name, link):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as tar:
            item = tarfile.TarInfo(name)
            if link:
                item.type = tarfile.SYMTYPE
                item.linkname = "/etc/passwd"
            else:
                item.size = 2
            tar.addfile(item, None if link else io.BytesIO(b"ok"))
        return data.getvalue()
    assert unpack_workspace(archive("./src/Token.sol", False)) == {"src/Token.sol": b"ok"}
    with pytest.raises(ValueError, match="unsafe path|link or special"):
        unpack_workspace(archive(name, link))


@pytest.mark.parametrize("free_check,compile_error", [(False, False), (True, False), (True, True)])
def test_combined_scoring_and_free_check_pipeline(tmp_path, monkeypatch, free_check, compile_error):
    import ethevals.scorers as scorers
    config = load_config()
    config.models["opus"].model = "mockllm/model"
    evaluation = load_eval(BUILD, config)
    task = build_task(evaluation, config, None if free_check else "opus", "internet", "reference" if free_check else None, 1)
    # Exercise real task scoring and row export with recorded sandbox output.
    # Docker and the real CLI have a separate end-to-end proof script.
    task.dataset[0].sandbox = None
    task.dataset[0].files = None
    task.solver = generate()
    task.model = get_model("mockllm/model")
    archives = []

    async def submitted():
        return {"src/Token.sol": b"contract Token {}", "foundry.toml": b"ffi = true", "test/Fake.t.sol": b"fake"}

    class Box:
        async def write_file(self, path, data):
            archives.append(data)

        async def exec(self, command, **kwargs):
            if command[0] in {"tar", "rm"}:
                return ExecResult(success=True, returncode=0, stdout="", stderr="")
            if compile_error:
                return ExecResult(success=False, returncode=1, stdout="", stderr="Error (2314): Expected semicolon.")
            output = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {"testSupply()": {"status": "Success"}}}})
            return ExecResult(success=True, returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(scorers, "workspace_files", submitted)
    monkeypatch.setattr(scorers, "sandbox", lambda name: Box())
    grades = [ModelOutput.from_content("mockllm/model", json.dumps(reply)) for reply in [
        {"passed": True, "reason": "Uses the OpenZeppelin ERC20 import."},
        {"passed": False, "reason": "Owner can seize tokens."},
    ]]
    log = eval(task, model_roles={"grader": get_model("mockllm/model", custom_outputs=grades)},
               log_dir=str(tmp_path / "logs"), display="none")[0]
    row = results_rows(log)[0]
    expected = {"forge:compile": {"passed": False, "reason": "Error (2314): Expected semicolon."}} if compile_error else {
        "forge:test/Token.t.sol:TokenTest:testSupply()": {"passed": True, "reason": "Test passed."}}
    if not free_check:
        expected.update({
            "rubric:uses_openzeppelin": {"passed": True, "reason": "Uses the OpenZeppelin ERC20 import."},
            "rubric:protects_holders": {"passed": False, "reason": "Owner can seize tokens."},
        })
    assert row["checks"] == expected
    assert row["status"] == ("passed" if free_check and not compile_error else "failed")
    if free_check:
        assert row["grader_tokens"] == 0
    else:
        assert row["grader_tokens"] > 0
    with tarfile.open(fileobj=io.BytesIO(archives[0]), mode="r:gz") as archive:
        assert sorted(archive.getnames()) == ["foundry.toml", "src/Token.sol", "test/BuilderPoints.t.sol"]
        assert b"ffi = false" in archive.extractfile("foundry.toml").read()


def test_eval_time_limit_overrides_type(tmp_path):
    folder = tmp_path / "concepts/quiz"
    shutil.copytree(ROOT / "evals/concepts/agent-registries", folder)
    path = folder / "eval.yaml"
    path.write_text(path.read_text() + "\ntime_limit: 123\n")
    config = load_config()
    config.token_limit = 4567
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    assert (task.time_limit, task.token_limit) == (123, 4567)
