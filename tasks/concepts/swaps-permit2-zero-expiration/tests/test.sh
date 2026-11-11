#!/bin/sh
set -eu
python3 /tests/judge_credentials.py
mkdir -p /logs/verifier
python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/opt")
from target_checks import final_reply

Path("/logs/verifier/final-reply.txt").write_text(final_reply(Path("/logs/agent/trajectory.json")))
PY
python3 /tests/install_judge.py
python3 /tests/agent_judge.py /logs/verifier/final-reply.txt
