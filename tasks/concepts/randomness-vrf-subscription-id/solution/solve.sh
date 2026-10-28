#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'JSON'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "No. A VRF 2.5 subscription id is a uint256, the keccak256 hash of the creator, a block hash, the coordinator and a nonce, so it does not fit in 64 bits."}]
}
JSON
