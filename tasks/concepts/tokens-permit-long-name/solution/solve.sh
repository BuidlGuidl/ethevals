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
      "message": "No: the token never deploys. The lock file holds OpenZeppelin Contracts 5.7.0, where the EIP712 constructor behind ERC20Permit reverts with StringTooLong for a name over 31 bytes, and this name is 33 bytes."
    }
  ]
}
EOF
