"""Name both stock images from their build inputs."""
import hashlib
from pathlib import Path

BUILD_INPUTS = {
    "runner": ("Dockerfile", "solc.json"),
    "chain": ("Chain.Dockerfile", "solc.json", "rpc_filter.py", "rpc_methods.json"),
}


def image_inputs(directory=Path(__file__).parent, image="runner"):
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in BUILD_INPUTS[image]}


def image_tag(directory=Path(__file__).parent, image="runner"):
    digest = hashlib.sha256()
    for name in BUILD_INPUTS[image]:
        digest.update(name.encode() + b"\0" + (directory / name).read_bytes() + b"\0")
    repository = "ethevals-solidity" if image == "runner" else "ethevals-chain"
    return repository + ":inputs-" + digest.hexdigest()[:16]


if __name__ == "__main__":
    for image in BUILD_INPUTS:
        print(image + ": " + image_tag(image=image))
