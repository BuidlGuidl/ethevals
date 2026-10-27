#!/bin/sh
set -eu
started_at=$(date +%s)
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
# Stop agent processes before executing untrusted build scripts, then again before the fork exists.
python3 /tests/stop-agent.py
cd /workspace
build_status=0
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u ANTHROPIC_AUTH_TOKEN -u EXA_API_KEY \
  runuser -u agent -- pnpm build > /logs/verifier/build.log 2>&1 || build_status=$?
typecheck_status=0
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u ANTHROPIC_AUTH_TOKEN -u EXA_API_KEY \
  runuser -u agent -- pnpm exec tsc --noEmit > /logs/verifier/typecheck.log 2>&1 || typecheck_status=$?
python3 /tests/stop-agent.py
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
export PLAYWRIGHT_BROWSERS_PATH=/root/voting-browsers
browser_status=0
node /tests/browser.mjs /workspace /logs/verifier > /logs/verifier/browser.log 2>&1 || browser_status=$?
rewardkit /tests
if [ "$browser_status" -ne 0 ] || [ -f /logs/verifier/trial-error.json ]; then
  exit 1
fi
STARTED_AT="$started_at" python3 - <<'PY'
import json
import os
import time
from pathlib import Path

Path('/logs/verifier/total-timing.json').write_text(json.dumps({
    'verifier_seconds': round(time.time() - int(os.environ['STARTED_AT']), 3),
}) + '\n')
PY
