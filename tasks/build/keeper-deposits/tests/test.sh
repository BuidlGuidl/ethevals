#!/bin/sh
set -eu
mkdir -p /logs/verifier
python3 /tests/verify.py > /logs/verifier/verify.log 2>&1
cp /opt/check_records.py /tests/check_records.py
rewardkit /tests
