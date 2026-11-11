import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ethevals.checks import read_reward
from test_judge_helpers import ROOT, load_helper

CODE_CHECKS = {
    'swap-page': ['swaps_assets', 'cut_only_on_swap', 'exact_approvals', 'finite_deadline', 'native_eth', 'routers_empty'],
    'aave-savings-page': ['deposit_usdc', 'withdraw_partial', 'withdraw_all', 'deposit_usdt_leftover_allowance', 'refuses_over_cap'],
}


def page_driver(tmp_path, monkeypatch, task):
    tests, output, home, code = (tmp_path / name for name in ('tests', 'output', 'home', 'code'))
    shutil.copytree(ROOT / 'tasks/build' / task / 'tests', tests)
    # test.sh stops Linux agent processes before this driver; the host unit check starts after that step.
    (tests / 'stop-agent.py').unlink()
    # This driver reads only the check names. Transaction logic has its own Node tests and image dependencies.
    (tests / 'checks.mjs').write_text('export const CHECKS = ' + json.dumps(CODE_CHECKS[task]) + ';\n')
    for directory in (output, home, code):
        directory.mkdir()
    shutil.copyfile(ROOT / 'runner/ethevals/images/check_records.py', tests / 'check_records.py')
    monkeypatch.syspath_prepend(str(tests))
    for name in ('judge_credentials', 'agent_judge', 'install_judge'):
        monkeypatch.setitem(sys.modules, name, load_helper(name, tests / (name + '.py')))
    module = load_helper('page_verifier', tests / 'run_reward.py')
    monkeypatch.setattr(module, 'TESTS', tests)
    monkeypatch.setattr(module, 'OUTPUT', output)
    monkeypatch.setattr(module, 'JUDGE', tmp_path / 'judge')
    monkeypatch.setattr(module, 'prepare', lambda inputs: home)
    monkeypatch.setattr(module, 'copy_submission', lambda: code)
    clean = dict(os.environ, CHECKS_FILE=str(output / 'checks.json'))
    monkeypatch.setattr(module.os, 'environ', dict(clean))
    monkeypatch.setattr(module, 'environment', lambda home: dict(clean))
    return module, tests, output


@pytest.mark.parametrize('task', ['swap-page', 'aave-savings-page'])
def test_compile_failure_writes_failed_code_checks_and_criteria_without_tools_or_a_session(tmp_path, monkeypatch, task):
    module, tests, output = page_driver(tmp_path, monkeypatch, task)
    (output / 'checks.json').write_text('{"compile":{"passed":false,"reason":"Build failed."}}')

    def forbidden(*args, **kwargs):
        raise AssertionError('A compile failure must not install tools or start a page judge.')

    monkeypatch.setattr(module, 'install', forbidden)
    import rewardkit.reward
    monkeypatch.setattr(rewardkit.reward, 'arun_agent', forbidden)
    popen = subprocess.Popen

    def start(command, *args, **kwargs):
        if command == ['node', '/tests/session.mjs']:
            forbidden()
        return popen(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', start)
    module.main()
    rewards, checks = read_reward(output)
    assert rewards == {'reward': 0.0}
    assert {name: check['passed'] for name, check in checks.items()} == dict.fromkeys(
        ['compile', 'swaps_assets', 'cut_only_on_swap', 'exact_approvals', 'finite_deadline', 'native_eth', 'routers_empty',
         'shows_received', 'honors_minimum', 'explains_price_change'] if task == 'swap-page' else
        ['compile', 'deposit_usdc', 'withdraw_partial', 'withdraw_all', 'deposit_usdt_leftover_allowance', 'refuses_over_cap',
         'shows_deposit', 'shows_apy', 'explains_supply_cap', 'switches_and_continues'], False)
    assert checks['compile']['reason'] == 'Build failed.'
    assert checks['swaps_assets' if task == 'swap-page' else 'deposit_usdc']['reason'] == (
        'The project did not compile. See build.log and typecheck.log.')
    assert checks['shows_received' if task == 'swap-page' else 'shows_deposit']['reason'] == (
        'The project did not compile, so the judge did not open the page.')


@pytest.mark.parametrize('task', ['swap-page', 'aave-savings-page'])
def test_an_outdated_walkthrough_writes_an_explicit_fail_instead_of_empty_session_results(tmp_path, monkeypatch, task):
    module, tests, output = page_driver(tmp_path, monkeypatch, task)
    (tests / 'page.toml').unlink()
    (output / 'checks.json').write_text('{"compile":{"passed":true,"reason":"Built."}}')
    monkeypatch.setattr(module, 'install', lambda: None)

    class Session:
        def __init__(self, *args, **kwargs):
            (output / 'session.json').write_text('{"control":"http://unused","rpc":"http://unused","origin":"http://unused","wallet":"0x1"}')

        def terminate(self):
            pass

        def wait(self, **kwargs):
            return 0

    popen, run = subprocess.Popen, subprocess.run
    monkeypatch.setattr(subprocess, 'Popen', lambda command, *args, **kwargs:
        Session() if command == ['node', '/tests/session.mjs'] else popen(command, *args, **kwargs))
    monkeypatch.setattr(subprocess, 'run', lambda command, *args, **kwargs:
        subprocess.CompletedProcess(command, 2) if command == ['node', '/tests/solution-walk.mjs'] else run(command, *args, **kwargs))

    def no_finish(*args, **kwargs):
        raise AssertionError('A mismatched solution must keep its explicit failure reason.')

    monkeypatch.setattr(module.urllib.request, 'urlopen', no_finish)
    module.main()
    rewards, checks = read_reward(output)
    assert rewards == {'reward': 0.0}
    assert checks.pop('compile') == {'passed': True, 'reason': 'Built.'}
    assert list(checks.values()) == [{'passed': False, 'reason': "The solution walk-through's source hash is out of date."}] * (6 if task == 'swap-page' else 5)
