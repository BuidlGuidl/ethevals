#!/bin/sh
set -eu
python3 /tests/payout_checks.py
cp /opt/check_records.py /tests/check_records.py
rewardkit /tests
