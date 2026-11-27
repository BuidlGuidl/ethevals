#!/bin/sh
set -eu
cd /workspace
test -r chain_context.json
test ! -r /private/private_chain_context.json
python3 /solution/shut_off.py
