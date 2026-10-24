#!/bin/sh
set -eu
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
# Agent processes must not reach the verifier's private fork.
pkill -KILL -u agent || test "$?" = 1
python3 /tests/run.py
cp /opt/check_records.py /tests/check_records.py
rewardkit /tests
