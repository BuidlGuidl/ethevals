#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'EOF'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "\"VaultDeposit witness)TokenPermissions(address token,uint256 amount)VaultDeposit(address receiver)\"\n\nThis closes the Permit2 stub and appends the referenced types in alphabetical order."}]
}
EOF
