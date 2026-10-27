#!/bin/sh
set -eu
mkdir -p /logs/verifier
python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/opt")
from target_checks import final_reply

Path("/logs/verifier/final-reply.txt").write_text(final_reply(Path("/logs/agent/trajectory.json")))
PY
rewardkit /tests
