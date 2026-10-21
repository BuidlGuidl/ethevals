"""Name stock images from their build inputs."""
import hashlib
from pathlib import Path

BUILD_INPUTS = {
    "quiz": ("Quiz.Dockerfile", "target_checks.py"),
    "chain": ("Chain.Dockerfile", "rpc_filter.py", "rpc_methods.json", "ChainSetup.sol",
              "setup-foundry.toml", "verify-foundry.toml", "forge_checks.py", "start_chain.py"),
}


def image_tag(directory=Path(__file__).parent, image="chain"):
    digest = hashlib.sha256()
    for name in BUILD_INPUTS[image]:
        digest.update(name.encode() + b"\0" + (directory / name).read_bytes() + b"\0")
    repository = {"chain": "ethevals-chain", "quiz": "ethevals-quiz"}[image]
    return repository + ":inputs-" + digest.hexdigest()[:16]


if __name__ == "__main__":
    for image in BUILD_INPUTS:
        print(image + "=" + image_tag(image=image))
