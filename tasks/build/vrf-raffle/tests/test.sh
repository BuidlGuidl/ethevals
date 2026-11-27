#!/bin/sh
set -eu
export PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
export DEPLOYER_PRIVATE_KEY="$PRIVATE_KEY"
# The account behind PRIVATE_KEY is also the sender, so msg.sender and the broadcaster agree.
export FOUNDRY_SENDER=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
# The copies of Chainlink's mock under tests/chainlink/ carry floating pragmas; offline keeps Forge on the image's 0.8.30.
export FOUNDRY_OFFLINE=true
python3 /opt/forge_checks.py
cp /opt/check_records.py /tests/check_records.py
rewardkit /tests
