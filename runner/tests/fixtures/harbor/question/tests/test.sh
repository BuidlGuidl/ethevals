#!/bin/sh
set -eu
python3 - <<'PY'
import json
from pathlib import Path

trajectory = Path("/logs/agent/trajectory.json")
passed = trajectory.exists() and json.loads(trajectory.read_text())["steps"][-1]["message"] == "metre"
output = Path("/logs/verifier")
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"unit": {
    "passed": passed, "reason": "The final reply matches." if passed else "The final reply is absent or differs."
}}))
(output / "reward.txt").write_text(str(int(passed)))
PY
