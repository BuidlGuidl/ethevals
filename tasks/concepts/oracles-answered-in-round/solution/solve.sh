#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'TRAJECTORY'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "No. Chainlink marks answeredInRound as deprecated, so compare updatedAt with the feed's heartbeat instead."}]
}
TRAJECTORY
