import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ethevals.job_config import load_job, check_judge_key

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / 'tasks/concepts/wallet-atomic-ready/tests'


def modules(monkeypatch):
    def read(name, file):
        spec = importlib.util.spec_from_file_location(name, file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    auth = read('plain_credentials', TESTS / 'judge_credentials.py')
    monkeypatch.setitem(sys.modules, 'judge_credentials', auth)
    return auth, read('plain_agent_judge', TESTS / 'agent_judge.py')


def clear_credentials(monkeypatch):
    for name in ('CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'REWARDKIT_FORCE_SUBSCRIPTION', 'ETHEVALS_REGRADE_ITEM'):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize('plan,key,winner', [
    ('offline-plan-token', None, 'CLAUDE_CODE_OAUTH_TOKEN'),
    (None, 'offline-api-key', 'ANTHROPIC_API_KEY'),
    ('offline-plan-token', 'offline-api-key', 'CLAUDE_CODE_OAUTH_TOKEN'),
])
def test_plain_task_starts_its_judge_with_the_selected_credential(tmp_path, monkeypatch, plan, key, winner):
    clear_credentials(monkeypatch)
    auth, helper = modules(monkeypatch)
    for name, value in [('CLAUDE_CODE_OAUTH_TOKEN', plan), ('ANTHROPIC_API_KEY', key)]:
        if value:
            monkeypatch.setenv(name, value)
    output = tmp_path / 'verifier'
    output.mkdir()
    monkeypatch.setenv('REWARDKIT_LOG_DIR', str(output))
    monkeypatch.setattr(helper, 'prepare', lambda inputs: tmp_path / 'home')
    monkeypatch.setattr(helper.shutil, 'which', lambda name: '/stand-in/rewardkit')
    calls = []

    def start(command, *, env, check):
        calls.append((command, env))
        (output / 'reward-details.json').write_text('{}')

    monkeypatch.setattr(helper.subprocess, 'run', start)
    helper.run([])
    command, environment = calls[0]
    assert len(calls) == 1 and command[:2] == ['/stand-in/rewardkit', '/tests']
    assert environment[winner] == (plan if winner == 'CLAUDE_CODE_OAUTH_TOKEN' else key)
    loser = 'ANTHROPIC_API_KEY' if winner == 'CLAUDE_CODE_OAUTH_TOKEN' else 'CLAUDE_CODE_OAUTH_TOKEN'
    assert loser not in environment
    assert environment['REWARDKIT_FORCE_SUBSCRIPTION'] == ('1' if plan else '')


def test_no_credential_prints_one_line_removes_stale_scores_and_starts_no_judge(tmp_path):
    env = dict(os.environ)
    for name in ('CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'REWARDKIT_FORCE_SUBSCRIPTION', 'ETHEVALS_REGRADE_ITEM'):
        env.pop(name, None)
    env['REWARDKIT_LOG_DIR'] = str(tmp_path)
    (tmp_path / 'reward.json').write_text('{"reward":1}')
    completed = subprocess.run([sys.executable, str(TESTS / 'judge_credentials.py')], env=env, capture_output=True, text=True)
    reason = 'The judge needs CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY.'
    assert (completed.returncode, completed.stdout, completed.stderr) == (1, '', reason + '\n')
    assert (tmp_path / 'judge-error.txt').read_text() == reason + '\n'
    assert not (tmp_path / 'reward.json').exists()


def test_board_plan_override_never_falls_back_to_an_api_key(monkeypatch):
    clear_credentials(monkeypatch)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'offline-api-key')
    settings = load_job().judge
    assert (settings.paid_by, settings.key_env) == ('plan', 'CLAUDE_CODE_OAUTH_TOKEN')
    with pytest.raises(ValueError, match='CLAUDE_CODE_OAUTH_TOKEN'):
        check_judge_key(settings)
    for name, value in settings.environment().items():
        monkeypatch.setenv(name, value)
    auth, _ = modules(monkeypatch)
    with pytest.raises(SystemExit, match='CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY'):
        auth.credentials()


def test_cached_regrade_and_free_code_checks_need_no_credential(tmp_path, monkeypatch):
    clear_credentials(monkeypatch)
    auth, _ = modules(monkeypatch)
    assert auth.credentials(tmp_path) == {}
    item = tmp_path / 'item.json'
    item.write_text('{"judge_required":false}')
    monkeypatch.setenv('ETHEVALS_REGRADE_ITEM', str(item))
    assert auth.credentials() == {}


def test_native_tasks_ship_the_same_credential_rule_and_optional_host_inputs(monkeypatch):
    from harbor.utils.env import resolve_env_vars
    import tomllib

    clear_credentials(monkeypatch)
    canonical = (TESTS / 'judge_credentials.py').read_bytes()
    files = list((ROOT / 'tasks').glob('*/*/tests/judge_credentials.py'))
    assert len(files) == 9
    for file in files:
        assert file.read_bytes() == canonical
        task = tomllib.loads((file.parent.parent / 'task.toml').read_text())
        assert resolve_env_vars(task['verifier']['env']) == {'CLAUDE_CODE_OAUTH_TOKEN': '', 'ANTHROPIC_API_KEY': ''}


def test_rewardkit_can_import_the_task_helper_without_the_task_on_pythonpath(tmp_path):
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    command = ('import importlib.util; '
        f's=importlib.util.spec_from_file_location("discovered_helper",{str(TESTS / "agent_judge.py")!r}); '
        'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
        'assert callable(m.credentials) and callable(m.run)')
    completed = subprocess.run([sys.executable, '-I', '-c', command], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
