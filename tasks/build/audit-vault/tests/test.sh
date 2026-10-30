#!/bin/sh
set -eu
mkdir -p /logs/verifier
if [ -f /workspace/findings.md ]; then
  cp /workspace/findings.md /logs/verifier/findings.md
else
  printf 'No findings.md was written.\n' > /logs/verifier/findings.md
fi
rewardkit /tests
