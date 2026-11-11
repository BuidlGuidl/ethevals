#!/bin/sh
set -eu
python3 /tests/sale_checks.py
cp /opt/check_records.py /tests/check_records.py
python3 /opt/agent_judge.py /logs/verifier/script-source.txt /logs/verifier/chain-evidence.json /chain/chain_context.json
