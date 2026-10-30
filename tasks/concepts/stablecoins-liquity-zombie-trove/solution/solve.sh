#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'TRAJECTORY'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "Zombie. A Trove redeemed below the 2,000 BOLD minimum debt is tagged zombie and taken off the sorted list until its owner tops it up above the minimum or closes it."}]
}
TRAJECTORY
