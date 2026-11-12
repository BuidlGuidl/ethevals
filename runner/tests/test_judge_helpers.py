import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUDGE_VARIANTS = {
    'file judge': ('act/treasury-eth-sale', [
        'act/treasury-eth-sale', 'build/voting-page',
        'concepts/governance-arbitrum-block-clock', 'concepts/smart-accounts-userop-hash-v08',
        'concepts/swaps-permit2-zero-expiration', 'concepts/wallet-atomic-ready', 'concepts/wallet-batch-status-600']),
    'page judge': ('build/swap-page', ['build/swap-page', 'build/aave-savings-page']),
}


def load_helper(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('variant', JUDGE_VARIANTS)
def test_task_helpers_equal_their_named_variant(variant):
    source, tasks = JUDGE_VARIANTS[variant]
    for task in tasks:
        for name in ('judge-settings.json', 'agent_judge.py', 'install_judge.py'):
            file = ROOT / 'tasks' / task / 'tests' / name
            assert file.read_bytes() == (ROOT / 'tasks' / source / 'tests' / name).read_bytes(), (
                f'{file}: copy the {variant} helper from tasks/{source}/tests/{name}')
    if variant == 'page judge':
        assert (ROOT / 'tasks/build/swap-page/tests/run_reward.py').read_bytes() == (
            ROOT / 'tasks/build/aave-savings-page/tests/run_reward.py').read_bytes()


def test_page_rewardkit_private_calls_have_the_expected_version():
    installed = importlib.metadata.version('harbor-rewardkit')
    assert installed == '0.2.3', (
        f'Page verifiers use RewardKit 0.2.3 private calls; found {installed}. '
        'Review both run_reward.py files before changing the RewardKit pin.')


@pytest.mark.parametrize('variant', JUDGE_VARIANTS)
def test_cached_judge_install_does_not_read_the_network(tmp_path, monkeypatch, variant):
    source, _ = JUDGE_VARIANTS[variant]
    tests = ROOT / 'tasks' / source / 'tests'
    module = load_helper('cached_installer', tests / 'install_judge.py')
    item = tmp_path / 'item.json'
    item.write_text('{"judge_required":false}')
    monkeypatch.setenv('ETHEVALS_REGRADE_ITEM', str(item))
    original_path = Path
    monkeypatch.setattr(module, 'Path', lambda value: tmp_path / value.lstrip('/') if str(value).startswith('/root/') else original_path(value))
    requests = []

    def download(request, **kwargs):
        requests.append(request.full_url)
        raise RuntimeError('A live judge needs its pinned CLI download.')

    monkeypatch.setattr(module.urllib.request, 'urlopen', download)
    module.install(tests)
    assert (requests, list(tmp_path.glob('root/**/*'))) == ([], [])
    item.write_text('{"judge_required":true}')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    with pytest.raises(RuntimeError, match='A live judge needs its pinned CLI download.'):
        module.install(tests)
    assert requests == ['https://downloads.claude.ai/claude-code-releases/2.1.321/linux-x64/claude']


def test_page_packages_install_outside_rewardkit_discovery(tmp_path, monkeypatch):
    module = load_helper('page_installer', ROOT / 'tasks/build/swap-page/tests/install_judge.py')
    tests, output = tmp_path / 'tests', tmp_path / 'output'
    (tests / 'mcp').mkdir(parents=True)
    output.mkdir()
    for name in ('package.json', 'package-lock.json'):
        (tests / 'mcp' / name).write_text('{"name":"pinned-mcp"}')
    chrome = tmp_path / 'root/savings-browsers/chromium-1/chrome-linux/chrome'
    chrome.parent.mkdir(parents=True)
    chrome.write_text('browser')
    monkeypatch.setattr(module, 'Path', lambda value: tmp_path / value.lstrip('/'))
    calls = []

    def npm(command, **kwargs):
        packages = Path(command[3])
        calls.append((command, (packages / 'package.json').read_text(), (packages / 'package-lock.json').read_text()))
        dependency = packages / 'node_modules/dependency'
        dependency.mkdir(parents=True)
        (dependency / 'surprise.py').write_text('raise RuntimeError("RewardKit must not import this dependency")')

    monkeypatch.setattr(module.subprocess, 'run', npm)
    assert module.install_browser(tests, output) == str(chrome)
    assert calls == [(['npm', 'ci', '--prefix', str(tmp_path / 'root/judge-mcp'), '--ignore-scripts', '--silent'],
                      '{"name":"pinned-mcp"}', '{"name":"pinned-mcp"}')]
    from rewardkit.runner import _discover_layout
    layout = _discover_layout(tests, tmp_path)
    assert (layout.dimensions, (tmp_path / 'root/judge-browser').resolve()) == ({}, chrome)


@pytest.mark.parametrize('required', [False, True])
def test_regrade_check_installs_only_for_an_uncached_judge(tmp_path, monkeypatch, required):
    import rewardkit.runner
    from ethevals import regrade_checks
    from types import SimpleNamespace

    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'install_judge.py').write_text('present')
    item = tmp_path / 'item.json'
    item.write_text(json.dumps({'judge_required': required}))
    monkeypatch.setenv('ETHEVALS_REGRADE_ITEM', str(item))
    monkeypatch.setattr(regrade_checks, 'Path', lambda value: tests / str(value).removeprefix('/tests/') if str(value).startswith('/tests/') else Path(value))
    events = []
    monkeypatch.setitem(sys.modules, 'install_judge', SimpleNamespace(install=lambda: events.append('install')))

    def replay(path):
        events.append(('replay', path))
        (tmp_path / 'reward.json').write_text('{"reward":1.0}')

    monkeypatch.setattr(regrade_checks, 'replay', replay)
    monkeypatch.setattr(rewardkit.runner, 'run', rewardkit.runner.run)
    regrade_checks.check_one()
    assert (events, json.loads((tmp_path / 'reward.json').read_text())) == (
        (['install'] if required else []) + [('replay', '/tests')], {'reward': 1.0})
