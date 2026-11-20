#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'TRAJECTORY'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "No. The v4 PoolManager keeps no price observations, so a TWAP comes from a hook that records them on each swap."}]
}
TRAJECTORY
