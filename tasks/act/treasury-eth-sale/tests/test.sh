#!/bin/sh
set -eu
python3 /tests/judge_credentials.py
python3 /tests/sale_checks.py
cp /opt/check_records.py /tests/check_records.py
python3 /tests/install_judge.py
python3 /tests/agent_judge.py /logs/verifier/script-source.txt /logs/verifier/chain-evidence.json /logs/agent/trajectory.json
