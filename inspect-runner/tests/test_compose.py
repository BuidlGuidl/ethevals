from dataclasses import replace
from pathlib import Path
import io
import shutil
import tarfile

from ethevals.files import inline_file
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.sandboxes import IMAGES, unpack_workspace, validate_compose
import pytest
import yaml

from support import build_task, fixture_config


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"


def test_agent_sample_contains_only_workspace_files():
    config = fixture_config()
    config.agents["opus"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    task = build_task(load_eval(BUILD, config), config, "opus", "internet", None, 1)
    sample = task.dataset[0]
    assert sample.files == {
        "/workspace/foundry.toml": inline_file((IMAGES / "foundry.toml").read_bytes()),
        "/workspace/src/BuilderPoints.sol": inline_file((BUILD / "workspace/src/BuilderPoints.sol").read_bytes()),
    }
    assert (sample.sandbox.type, Path(sample.sandbox.config).name) == ("ethevals_docker", "compose.yaml")


@pytest.mark.parametrize("extra,reason", [
    ({"privileged": True}, "privileged"),
    ({"volumes": ["/tmp:/host"]}, "host mounts"),
    ({"volumes": [{"type": "bind", "source": "/tmp", "target": "/host"}]}, "host mounts"),
    ({"network_mode": "host"}, "forbidden options"),
    ({"build": "."}, "forbidden options"),
    ({"environment": {"KEY": None}}, "inherited host environment"),
    ({"networks": ["private", "internet"]}, "private network"),
    ({"mem_limit": 0}, "positive mem_limit"),
])
def test_unsafe_compose_is_rejected(tmp_path, extra, reason):
    data = {"services": {"database": {"image": "postgres:17", "mem_limit": "512m", **extra}}}
    with pytest.raises(ValueError, match=reason):
        validate_compose(tmp_path / "compose.yaml", data=yaml.safe_dump(data).encode())


def test_concurrency_must_fit_docker_memory(monkeypatch):
    from types import SimpleNamespace
    from ethevals.preparation import check_capacity
    monkeypatch.setattr("ethevals.preparation.docker_command", lambda args: SimpleNamespace(stdout=str(8 * 1024**3)))
    config = fixture_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    check_capacity(config, [evaluation])
    config.concurrency = 3
    with pytest.raises(ValueError, match="5.25 GiB per concurrent epoch plus 1 GiB for the host"):
        check_capacity(config, [evaluation])


def test_extra_services_and_real_memory_limits(tmp_path, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from ethevals.preparation import check_capacity
    from ethevals.sandboxes import merged_compose
    extra = {"services": {name: {"image": "postgres:17", "mem_limit": "512m"}
                          for name in ("one", "two", "three", "four")}}
    config = fixture_config()
    evaluation = load_eval(BUILD, config)
    evaluation = replace(evaluation, files={**evaluation.files, "compose.yaml": yaml.safe_dump(extra).encode()})
    services = merged_compose(evaluation)["services"]
    assert set(services) == {"default", "scorer", "one", "two", "three", "four"}
    assert services["four"] == {"image": "postgres:17", "mem_limit": "512m", "networks": ["private"]}
    monkeypatch.setattr("ethevals.preparation.docker_command", lambda args: SimpleNamespace(stdout=str(7 * 1024**3)))
    with pytest.raises(ValueError, match="7 GiB per concurrent epoch plus 1 GiB"):
        check_capacity(config, [evaluation])


@pytest.mark.parametrize("name", ["default", "scorer", "chain"])
def test_author_cannot_replace_runner_services(tmp_path, name):
    with pytest.raises(ValueError, match="belong to the runner"):
        validate_compose(tmp_path / "compose.yaml", data=yaml.safe_dump({"services": {name: {}}}).encode())


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


@pytest.mark.parametrize("value", ["$SECRET_PROBE", "${SECRET_PROBE}", "$$literal/$SECRET_PROBE"])
def test_compose_rejects_both_interpolation_forms(tmp_path, value):
    data = yaml.safe_load((IMAGES / "stock.compose.yaml").read_text())
    data["services"]["default"]["environment"] = {"LEAK": value}
    path = tmp_path / "compose.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="host environment substitution"):
        validate_compose(path)


def test_compose_checks_decoded_values_and_allows_literal_dollars(tmp_path):
    text = 'services:\n  extra:\n    image: postgres:17\n    mem_limit: 512m\n    environment: {VALUE: "\\u0024SECRET_PROBE"}\n'
    path = tmp_path / "compose.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match="host environment substitution"):
        validate_compose(path)
    path.write_text(text.replace('\\u0024SECRET_PROBE', '$$SECRET_PROBE'))
    assert yaml.safe_load(validate_compose(path))["services"]["extra"]["environment"] == {"VALUE": "$$SECRET_PROBE"}


def test_compose_rejects_binary_yaml(tmp_path):
    document = yaml.safe_load((IMAGES / "stock.compose.yaml").read_bytes())
    document["services"]["default"]["environment"] = {"TOKEN": b"$SECRET_PROBE"}
    with pytest.raises(ValueError, match="unsupported YAML scalar"):
        validate_compose(tmp_path / "compose.yaml", data=yaml.safe_dump(document).encode())


def test_compose_runs_the_normalized_captured_document(tmp_path):
    config = fixture_config()
    evaluation = load_eval(BUILD, config)
    raw = b"services:\n  database:\n    image: postgres:17\n    mem_limit: 512m\n# author bytes\n"
    evaluation = replace(evaluation, files={**evaluation.files, "compose.yaml": raw})
    path = prepare_compose(evaluation, tmp_path)
    assert yaml.safe_load(path.read_bytes())["services"]["database"] == {"image": "postgres:17", "mem_limit": "512m", "networks": ["private"]}
    assert path.read_bytes() != raw


def test_runner_image_changes_leave_eval_hash_unchanged(tmp_path, monkeypatch):
    import ethevals.sandboxes as sandboxes
    from ethevals.sandboxes import merged_compose
    images = tmp_path / "images"
    shutil.copytree(IMAGES, images)
    monkeypatch.setattr(sandboxes, "IMAGES", images)
    folder = tmp_path / "building" / "extra"
    shutil.copytree(ROOT / "evals/building/erc20-points-token", folder)
    (folder / "compose.yaml").write_text("services:\n  database:\n    image: postgres:17\n    mem_limit: 512m\n")
    before = load_eval(folder, fixture_config())
    first = merged_compose(before)["services"]["default"]["image"]
    dockerfile = images / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text() + "\nLABEL test=changed\n")
    after = load_eval(folder, fixture_config())
    merged = merged_compose(after)["services"]
    assert after.hash == before.hash
    assert merged["default"]["image"] != first
    assert merged["database"] == {"image": "postgres:17", "mem_limit": "512m", "networks": ["private"]}
