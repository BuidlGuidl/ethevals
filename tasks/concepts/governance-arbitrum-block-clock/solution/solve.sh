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
      "message": "About 7 days. Arbitrum One's block.number approximates Ethereum L1 blocks, about 12 seconds each."
    }
  ]
}
EOF
