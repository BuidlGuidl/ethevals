#!/bin/sh
set -eu
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
# Agent processes must not reach the verifier's private fork. The image has no pkill.
agent=$(id -u agent)
for proc in /proc/[0-9]*; do
  pid=${proc#/proc/}
  # PID 1 keeps the container up and ignores SIGKILL anyway.
  if [ "$pid" != 1 ] && [ "$(stat -c %u "$proc" 2>/dev/null)" = "$agent" ]; then kill -KILL "$pid" 2>/dev/null || true; fi
done
python3 /tests/verify.py > /logs/verifier/verify.log 2>&1
cp /opt/check_records.py /tests/check_records.py
rewardkit /tests
