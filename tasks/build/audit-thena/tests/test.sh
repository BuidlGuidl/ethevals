#!/bin/sh
set -eu
python3 /tests/judge_credentials.py
mkdir -p /logs/verifier
if [ -f /workspace/findings.md ]; then
  cp /workspace/findings.md /logs/verifier/findings.md
fi
python3 /tests/install_judge.py
python3 /tests/agent_judge.py /logs/verifier/findings.md
