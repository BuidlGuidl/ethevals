"""Image names identify build inputs."""
import shutil
from pathlib import Path

import pytest
import yaml

from ethevals.config import load_config
from ethevals.images.tag import BUILD_INPUTS, image_tag
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.sandboxes import IMAGES

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("image,eval_path", [
    ("runner", "building/erc20-points-token"),
    ("chain", "transactions/send-six-decimal-token"),
])
def test_build_inputs_rename_images_and_reject_stale_compose(tmp_path, monkeypatch, image, eval_path):
    import ethevals.preparation as preparation
    import ethevals.sandboxes as sandboxes

    images = tmp_path / "images"
    shutil.copytree(IMAGES, images)
    monkeypatch.setattr(preparation, "IMAGES", images)
    monkeypatch.setattr(sandboxes, "IMAGES", images)
    evaluation = load_eval(ROOT / "evals" / eval_path, load_config())
    original = image_tag(images, image)
    foundry = images / "foundry.toml"
    foundry.write_text(foundry.read_text() + "optimizer = true\n")
    assert image_tag(images, image) == original

    for name in BUILD_INPUTS[image]:
        before = image_tag(images, image)
        path = images / name
        path.write_bytes(path.read_bytes() + b"\n")
        assert image_tag(images, image) != before
        with pytest.raises(ValueError, match="requires the .* image"):
            prepare_compose(evaluation, tmp_path / "stale")
        path.write_bytes(path.read_bytes()[:-1])


def test_both_compose_files_declare_the_computed_images():
    for name in ("stock.compose.yaml", "act.compose.yaml"):
        services = yaml.safe_load((IMAGES / name).read_bytes())["services"]
        assert services["default"]["image"] == services["scorer"]["image"] == image_tag(IMAGES)
        if "chain" in services:
            assert services["chain"]["image"] == image_tag(IMAGES, "chain")
