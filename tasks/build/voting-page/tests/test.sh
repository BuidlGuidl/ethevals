#!/bin/sh
set -eu
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
rm -f /logs/verifier/reward.json /logs/verifier/reward.txt /logs/verifier/reward-details.json \
  /logs/verifier/judge-response.json /logs/verifier/source-decisions.json /logs/verifier/rewardkit-request.json \
  /logs/verifier/source-evidence.txt /logs/verifier/source-manifest.json /logs/verifier/checks.json
python3 /tests/stop-agent.py
cd /workspace
build_status=0
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u ANTHROPIC_AUTH_TOKEN -u EXA_API_KEY -u CLAUDE_CODE_OAUTH_TOKEN \
  runuser -u agent -- pnpm build > /logs/verifier/build.log 2>&1 || build_status=$?
typecheck_status=0
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u ANTHROPIC_AUTH_TOKEN -u EXA_API_KEY -u CLAUDE_CODE_OAUTH_TOKEN \
  runuser -u agent -- pnpm exec tsc --noEmit > /logs/verifier/typecheck.log 2>&1 || typecheck_status=$?
python3 /tests/stop-agent.py
BUILD_STATUS="$build_status" TYPECHECK_STATUS="$typecheck_status" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, '/tests')
from source_bundle import bundle

build = int(os.environ['BUILD_STATUS'])
typecheck = int(os.environ['TYPECHECK_STATUS'])
passed = build == 0 and typecheck == 0
records = {'compile': {'passed': passed, 'reason':
    'pnpm build and pnpm exec tsc --noEmit passed.' if passed else
    f'pnpm build exited {build}; pnpm exec tsc --noEmit exited {typecheck}. See build.log and typecheck.log.'}}
if not Path('/tests/judge.toml').exists():
    def source_hashes(root):
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and p.suffix in {'.ts', '.tsx', '.js', '.jsx', '.html', '.css'}
            and not set(p.relative_to(root).parts) & {'contracts', 'node_modules', 'dist', '.git'}}
    changed = source_hashes(Path('/workspace')) != source_hashes(Path('/root/voting-starter'))
    records['free_submission_changed'] = {'passed': changed,
        'reason': 'Application source differs from the starter.' if changed else 'Application source matches the untouched starter.'}
Path('/logs/verifier/checks.json').write_text(json.dumps(records) + '\n')
if Path('/tests/judge.toml').exists():
    bundle(Path('/workspace'), Path('/chain/chain_context.json'), Path('/root/voting-contracts'), Path('/logs/verifier'))
PY
python3 /tests/run_reward.py
