#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'TRAJECTORY'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "The redeemed Trove's borrower. The fee is taken out of the collateral the redeemer draws and left in the Trove, where Liquity V1 had paid it to LQTY stakers."}]
}
TRAJECTORY
