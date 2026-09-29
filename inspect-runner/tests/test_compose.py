import io
import tarfile

from ethevals.sandboxes import IMAGES, unpack_workspace, validate_compose
import pytest
import yaml

@pytest.mark.parametrize("extra,reason", [
    ({"privileged": True}, "privileged"),
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


@pytest.mark.parametrize("name", ["scorer"])
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


@pytest.mark.parametrize("value", ["$SECRET_PROBE", "${SECRET_PROBE}"])
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
