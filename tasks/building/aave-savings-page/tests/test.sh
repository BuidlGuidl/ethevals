#!/bin/sh
set -eu
started_at=$(date +%s)
mkdir -p /logs/verifier
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
cp /opt/check_records.py /tests/check_records.py
export PLAYWRIGHT_BROWSERS_PATH=/root/savings-browsers
node --test /tests/*.test.mjs > /logs/verifier/browser-unit-tests.log 2>&1
python3 /tests/test_source_snapshot.py > /logs/verifier/source-tests.log 2>&1
node /tests/browser.mjs /workspace /logs/verifier > /logs/verifier/browser.log 2>&1
python3 /tests/source_snapshot.py /workspace /logs/verifier/project-source.txt
rewardkit /tests
STARTED_AT="$started_at" python3 - <<'PY'
import json
import os
import time
from pathlib import Path

Path('/logs/verifier/total-timing.json').write_text(json.dumps({
    'verifier_seconds': round(time.time() - int(os.environ['STARTED_AT']), 3),
}) + '\n')
PY
