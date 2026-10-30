#!/bin/sh
# Copy the audited project to a scratch folder, add the proof to its tests, and run it.
# Pass extra forge flags as arguments, such as a forge-std remapping outside the task image.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
cp -R "$here/../../environment/foundry.toml" "$here/../../environment/src" "$here/../../environment/test" "$work/"
cp "$here/Proof.t.sol" "$work/test/Proof.t.sol"
cd "$work"
forge test --match-contract '^Proof$' -vv "$@"
