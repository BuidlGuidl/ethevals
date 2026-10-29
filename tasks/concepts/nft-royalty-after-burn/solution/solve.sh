#!/bin/sh
set -eu
mkdir -p /logs/agent
cat > /logs/agent/trajectory.json <<'JSON'
{
  "schema_version": "ATIF-v1.7",
  "session_id": "solution",
  "agent": {"name": "oracle", "version": "1.0.0"},
  "steps": [{"step_id": 1, "source": "agent", "message": "Per-token. Since Contracts 5.0, ERC721Royalty no longer resets a token's royalty on burn, so the entry set with _setTokenRoyalty survives the burn and applies to the re-minted token 7."}]
}
JSON
