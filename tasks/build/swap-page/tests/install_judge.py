"""Install the pinned judge CLI only when this verifier contains an agent judge."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import tomllib
import urllib.request

VERSION = '2.1.321'
CHECKSUMS = {
    'x86_64': ('linux-x64', '426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f'),
    'aarch64': ('linux-arm64', '6bea0633074627ba79328e00115ed0588c3acf906a8463612b25db696dbfd3f0'),
}


def install_browser(tests, output):
    with (output / 'judge-browser-install.log').open('w') as log:
        subprocess.run(['npm', 'ci', '--prefix', str(tests / 'mcp'), '--ignore-scripts', '--silent'],
                       stdout=log, stderr=log, check=True)
    candidates = sorted(Path('/root/savings-browsers').glob('chromium-*/chrome-linux*/chrome'))
    if not candidates:
        raise FileNotFoundError('The page image has no existing Chromium executable.')
    browser = Path('/root/judge-browser')
    browser.unlink(missing_ok=True)
    browser.symlink_to(candidates[-1])
    return str(candidates[-1])


def install(tests=Path('/tests')):
    started = time.monotonic()
    if not any(tomllib.loads(path.read_text()).get('judge', {}).get('judge') == 'claude-code'
               for path in tests.glob('*.toml')):
        return
    binary = Path('/root/.local/bin/claude')
    current = subprocess.run([str(binary), '--version'], capture_output=True, text=True) if binary.exists() else None
    if current is None or current.returncode or current.stdout.split()[0] != VERSION:
        target, checksum = CHECKSUMS[platform.machine()]
        binary.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        download = binary.with_suffix('.download')
        request = urllib.request.Request(
            f'https://downloads.claude.ai/claude-code-releases/{VERSION}/{target}/claude',
            headers={'User-Agent': 'curl/8.0'})
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(request, timeout=180) as response, download.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != checksum:
                raise ValueError('The Claude Code download checksum differs from the pinned checksum.')
            download.chmod(0o700)
            download.replace(binary)
        finally:
            download.unlink(missing_ok=True)
    result = subprocess.run([str(binary), '--version'], capture_output=True, text=True, check=True)
    if result.stdout.split()[0] != VERSION:
        raise ValueError('The judge CLI version differs from the pinned version.')
    output = Path(os.environ.get('REWARDKIT_LOG_DIR', '/logs/verifier'))
    output.mkdir(parents=True, exist_ok=True)
    (output / 'judge-program.json').write_text(json.dumps({'program': 'claude-code', 'version': VERSION}) + '\n')
    browser = install_browser(tests, output)
    (output / 'judge-tools.json').write_text(json.dumps({'install_seconds': round(time.monotonic() - started, 3),
        'claude_code': VERSION, 'playwright_mcp': '0.0.85', 'existing_chromium': browser}) + '\n')


if __name__ == '__main__':
    install()
