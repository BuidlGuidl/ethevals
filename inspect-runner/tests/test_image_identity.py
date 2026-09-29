"""Image names identify build inputs."""
import shutil
from pathlib import Path

from support import fixture_config
from ethevals.images.tag import image_tag
from ethevals.loader import load_eval
from ethevals.sandboxes import IMAGES

ROOT = Path(__file__).resolve().parents[2]


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
