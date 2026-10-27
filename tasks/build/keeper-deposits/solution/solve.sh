#!/bin/sh
set -eu
cd /workspace
mkdir -p src script
cp /solution/KeeperDeposits.sol src/KeeperDeposits.sol
cp /solution/deposits.ts script/deposits.ts
