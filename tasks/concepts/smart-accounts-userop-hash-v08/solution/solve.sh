#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'EOF'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {
    "name": "oracle",
    "version": "1.0.0"
  },
  "steps": [
    {
      "step_id": 1,
      "source": "agent",
      "message": "An EIP-712 typed-data hash. EntryPoint v0.8 combines the UserOperation struct hash with its ERC4337 version 1 domain, chain ID, and EntryPoint address."
    }
  ]
}
EOF
