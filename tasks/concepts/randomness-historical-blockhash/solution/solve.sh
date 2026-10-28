#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'JSON'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "Yes. Call the EIP-2935 history contract at 0x0000F90827F1C53a10cb7A02335B175320002935 with the block number; it serves the last 8191 block hashes, while BLOCKHASH still stops at 256."}]
}
JSON
