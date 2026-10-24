"""Export contract sources and ABI arrays for the frontend project."""
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
destination = root / "frontend"
shutil.copytree(root / "src", destination / "src")
shutil.copytree(root / "lib/openzeppelin-contracts/contracts", destination / "lib/openzeppelin-contracts/contracts")
(destination / "abi").mkdir()
for name in ("Token", "Protocol", "VoteToken", "TokenGovernor", "TimelockController", "IVoteToken"):
    artifact = json.loads((root / f"out/{name}.sol/{name}.json").read_text())
    (destination / f"abi/{name}.json").write_text(json.dumps(artifact["abi"], indent=2) + "\n")
