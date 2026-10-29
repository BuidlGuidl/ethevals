"""Replay the two saved responses without a provider request."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile

import litellm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--boundary', type=Path, default=Path(__file__).parents[1] / 'tests/run_reward.py')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('saved_voting_boundary', args.boundary)
    boundary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boundary)
    fixtures = Path(__file__).with_name('fixtures')
    for trial in (1, 2):
        response = litellm.ModelResponse(**json.loads((fixtures / f'trial-{trial}-judge-response.json').read_text()))
        manifest = json.loads((fixtures / f'trial-{trial}-source-manifest.json').read_text())
        async def replay(**kwargs):
            return response
        with tempfile.TemporaryDirectory() as directory:
            restore = boundary.install_completion_boundary(Path(directory), manifest, replay)
            try:
                asyncio.run(litellm.acompletion(model='anthropic/claude-opus-5-5', reasoning_effort='high', messages=[]))
            except boundary.InvalidJudgeResponse as error:
                print(f'trial {trial}: {error}')
            else:
                raise AssertionError('An unchanged saved error reply must remain an error.')
            finally:
                restore()


if __name__ == '__main__':
    main()
