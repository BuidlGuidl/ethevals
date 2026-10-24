#!/bin/sh
set -eu
mkdir -p /logs/verifier
tar --exclude=node_modules --exclude=dist --exclude=.git \
    -czf /logs/verifier/project.tar.gz -C /workspace .
cp /chain/chain_context.json /logs/verifier/chain_context.json
cd /workspace
build_status=0
pnpm build > /logs/verifier/build.log 2>&1 || build_status=$?
typecheck_status=0
pnpm exec tsc --noEmit > /logs/verifier/typecheck.log 2>&1 || typecheck_status=$?
BUILD_STATUS="$build_status" TYPECHECK_STATUS="$typecheck_status" python3 - <<'PY'
import json
import os
from pathlib import Path

build = int(os.environ["BUILD_STATUS"])
typecheck = int(os.environ["TYPECHECK_STATUS"])
passed = build == 0 and typecheck == 0
reason = (
    "pnpm build and pnpm exec tsc --noEmit passed."
    if passed else
    f"pnpm build exited {build}; pnpm exec tsc --noEmit exited {typecheck}. See build.log and typecheck.log."
)
Path("/logs/verifier/checks.json").write_text(
    json.dumps({"compile": {"passed": passed, "reason": reason}}) + "\n"
)
PY
rewardkit /tests
