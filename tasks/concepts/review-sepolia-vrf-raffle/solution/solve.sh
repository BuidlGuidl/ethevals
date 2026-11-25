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
      "message": "Before the beta, fix the callback gas: with 100,000 the VRF callback will run out of gas on Sepolia, so no round can finish and the pot stays locked. Since Glamsterdam (EIP-8037), each new storage slot costs 97,920 state gas, and rawFulfillRandomWords writes new slots (winnings for a new winner, and round 0 to 1 on the first draw), so it needs about 255,000 gas the first time and about 157,000 later. Measure on Sepolia and raise the limit well above that, or store only the random word in the callback."
    }
  ]
}
EOF
