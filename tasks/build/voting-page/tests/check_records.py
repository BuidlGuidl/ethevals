"""Expose executed compilation and the explicit free-mode starter comparison."""
import json
import os
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion


@criterion(description="{check}")
def check_record(workspace: Path, check: str) -> dict:
    records = json.loads(Path(os.environ.get('CHECKS_FILE', '/logs/verifier/checks.json')).read_text())
    record = records[check]
    if type(record['passed']) is not bool or not isinstance(record['reason'], str) or not record['reason'].strip():
        raise ValueError('Each executed check needs a boolean result and a reason.')
    return {'score': record['passed'], 'reasoning': record['reason']}


rk.check_record('compile', name='compile')
if not Path(__file__).with_name('judge.toml').exists():
    rk.check_record('free_submission_changed', name='free_submission_changed')
