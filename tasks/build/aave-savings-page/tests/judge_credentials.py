"""Choose a judge credential without requiring the ETH Evals runner."""
import os
import json
from pathlib import Path
import tomllib

NEEDED = 'The judge needs CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY.'


def credentials(tests=None):
    tests = tests or Path(__file__).parent
    if not any(tomllib.loads(file.read_text()).get('judge', {}).get('judge') == 'claude-code'
               for file in tests.glob('*.toml')):
        return {}
    cached = os.environ.get('ETHEVALS_REGRADE_ITEM')
    if cached and json.loads(Path(cached).read_text()).get('judge_required') is False:
        return {}
    token = os.environ.get('CLAUDE_CODE_OAUTH_TOKEN', '').strip()
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    forced = os.environ.get('REWARDKIT_FORCE_SUBSCRIPTION', '').lower() in ('1', 'true', 'yes')
    if token:
        return {'CLAUDE_CODE_OAUTH_TOKEN': token, 'REWARDKIT_FORCE_SUBSCRIPTION': '1'}
    if key and not forced:
        return {'ANTHROPIC_API_KEY': key, 'REWARDKIT_FORCE_SUBSCRIPTION': ''}
    raise SystemExit(NEEDED)


if __name__ == '__main__':
    output = Path(os.environ.get('REWARDKIT_LOG_DIR', '/logs/verifier'))
    try:
        selected = credentials()
    except SystemExit as error:
        output.mkdir(parents=True, exist_ok=True)
        for name in ('reward.json', 'reward.txt'):
            (output / name).unlink(missing_ok=True)
        (output / 'judge-error.txt').write_text(str(error) + '\n')
        raise
    if selected:
        output.mkdir(parents=True, exist_ok=True)
        (output / 'judge-auth.json').write_text(json.dumps({'credential': next(iter(selected))}) + '\n')
