#!/bin/sh
set -eu
cd /workspace
test -r chain_context.json
test ! -r /private/private_chain_context.json
cat > /workspace/foundry.toml <<'EOF'
[profile.default]
src = "/solution"
remappings = ["forge-std/=/opt/solidity/lib/forge-std/src/"]
ffi = false
fs_permissions = [{access = "read", path = "/workspace/chain_context.json"}]
EOF
forge script /solution/solution.s.sol --root /workspace --broadcast --rpc-url http://chain:8545 --no-storage-caching
