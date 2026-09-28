"""Print the stock image tag after its inputs change."""
import hashlib
from pathlib import Path


def image_tag(directory=Path(__file__).parent):
    digest = hashlib.sha256()
    for name in ("Dockerfile", "foundry.toml"):
        digest.update(name.encode() + b"\0" + (directory / name).read_bytes() + b"\0")
    return "ethevals-solidity:inputs-" + digest.hexdigest()[:16]


if __name__ == "__main__":
    print(image_tag())
