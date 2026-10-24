#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'EOF'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "Only for an onchain-approved Safe message.\n\nThe SafeMessage hash for abi.encode(hash) must have a nonzero signedMessages entry, set through SignMessageLib.signMessage."}]
}
EOF
