#!/bin/sh
set -eu
python3 /tests/prepare.py
python3 /opt/forge_checks.py --private-context /tmp/aave-before.json
cp /opt/check_records.py /tests/check_records.py
rewardkit /tests
