import io
import json
import tarfile
import shutil
from pathlib import Path

import pytest
import yaml

from support import load_config
from ethevals.loader import load_eval
from support import build_task
from ethevals.sandboxes import IMAGES, unpack_workspace, validate_compose
from ethevals.scorers import forge_checks, rubric_reply
from ethevals.files import inline_file

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"
FORGE_OUTPUT = json.dumps({"test/Token.t.sol:TokenTest": {"test_results": {
    "testSupply()": {"status": "Success", "reason": None},
    "testTransfer()": {"status": "Failure", "reason": "Wrong recipient balance\nexpected 10"},
}}})


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


def test_rubric_boolean_and_reason():
    assert rubric_reply('{"passed": false, "reason": "Owner can seize tokens.\\nSee take()."}') == {
        "passed": False, "reason": "Owner can seize tokens. See take().",
    }
    with pytest.raises(ValueError, match="boolean"):
        rubric_reply('{"passed": "yes", "reason": "Fine"}')


def test_agent_sample_contains_only_workspace_files():
    config = load_config()
    config.agents["opus"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    task = build_task(load_eval(BUILD, config), config, "opus", "internet", None, 1)
    sample = task.dataset[0]
    assert sample.files == {
        "/workspace/foundry.toml": inline_file((IMAGES / "foundry.toml").read_bytes()),
        "/workspace/src/BuilderPoints.sol": inline_file((BUILD / "workspace/src/BuilderPoints.sol").read_bytes()),
    }
    assert (sample.sandbox.type, Path(sample.sandbox.config).name) == ("ethevals_docker", "stock.compose.yaml")


@pytest.mark.parametrize("service", ["default", "scorer"])
@pytest.mark.parametrize("limit", [None, "1g"])
def test_custom_compose_requires_bounded_memory(tmp_path, service, limit):
    data = yaml.safe_load((IMAGES / "stock.compose.yaml").read_bytes())
    data["services"]["default"].pop("build")
    data["services"][service]["mem_limit"] = limit
    with pytest.raises(ValueError, match="requires mem_limit:"):
        validate_compose(tmp_path / "compose.yaml", data=yaml.safe_dump(data).encode())


def test_concurrency_must_fit_docker_memory(monkeypatch):
    from types import SimpleNamespace
    from ethevals.preparation import check_capacity
    monkeypatch.setattr("ethevals.preparation.docker_command", lambda args: SimpleNamespace(stdout=str(8 * 1024**3)))
    config = load_config()
    check_capacity(config)
    config.concurrency = 3
    with pytest.raises(ValueError, match="5.25 GiB per concurrent epoch plus 1 GiB for the host"):
        check_capacity(config)


@pytest.mark.parametrize("extra,reason", [
    ({"privileged": True}, "privileged"),
    ({"volumes": ["/tmp:/host"]}, "volumes are forbidden"),
    ({"volumes": [{"type": "bind", "source": "/tmp", "target": "/host"}]}, "volumes are forbidden"),
    ({"network_mode": "host"}, "forbidden options"),
    ({"build": "."}, "forbidden options"),
    ({"environment": {"KEY": None}}, "inherited host environment"),
    ({"user": "root"}, "runner image and the agent user"),
    ({"image": "outside/agent:latest"}, "runner image and the agent user"),
    ({"environment": {"LD_PRELOAD": "/workspace/inject.so"}}, "startup environment overrides"),
])
def test_unsafe_compose_is_rejected(tmp_path, extra, reason):
    data = yaml.safe_load((IMAGES / "stock.compose.yaml").read_text())
    data["services"]["default"].pop("build")
    path = tmp_path / "compose.yaml"
    path.write_text(yaml.safe_dump(data))
    validate_compose(path)
    data["services"]["default"].update(extra)
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match=reason):
        validate_compose(path)


def test_services_cannot_join_internet(tmp_path):
    data = yaml.safe_load((IMAGES / "stock.compose.yaml").read_text())
    data["services"]["default"].pop("build")
    data["services"]["chain"] = yaml.safe_load((IMAGES / "act.compose.yaml").read_text())["services"]["chain"]
    data["services"]["chain"].pop("build")
    data["services"]["chain"]["networks"] = ["private", "internet"]
    path = tmp_path / "compose.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="only default can join internet"):
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
    from ethevals.scoring_base import SubmissionFailed
    with pytest.raises(SubmissionFailed, match="unsafe path|link or special"):
        unpack_workspace(archive(name, link))


def test_type_time_limit_reaches_task(tmp_path):
    folder = tmp_path / "concepts/quiz"
    shutil.copytree(ROOT / "evals/concepts/agent-registries", folder)
    path = folder / "eval.yaml"
    config = load_config()
    config.time_limits["quiz"] = 123
    config.cost_limit = 0.25
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    assert (task.working_limit, task.time_limit, task.cost_limit) == (123, 369, 0.25)
