"""Run pinned RewardKit with a bounded, validated completion boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ['PYTHON_DOTENV_DISABLED'] = '1'

import litellm
import rewardkit.judges as judges
from rewardkit.models import JudgeResult, Score
from rewardkit.runner import run

WORKFLOWS = ('lists_every_proposal', 'status_and_tallies_match', 'quorum_counts_for_only',
    'end_moves_with_late_quorum', 'wrap_then_delegate', 'votes_at_snapshot', 'canceled_status', 'already_voted')
MAX_OUTPUT_TOKENS = 24576
MAX_REQUEST_BYTES = 970_000


class InvalidJudgeResponse(ValueError):
    def __init__(self, reason, response):
        super().__init__(reason)
        self.response = response


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate judge reply key: {key}')
        result[key] = value
    return result


def validate_reply(text, manifest):
    reply = json.loads(text, object_pairs_hook=unique_object)
    if not isinstance(reply, dict) or set(reply) != set(WORKFLOWS) | {'guard'}:
        raise ValueError('Judge reply must contain every named workflow and guard exactly once.')
    allowed = {row['path']: row['last_line'] for row in manifest['files']}
    decisions = {}
    for name in WORKFLOWS:
        entry = reply[name]
        if not isinstance(entry, dict) or set(entry) != {'score', 'reasoning'} or entry['score'] not in ('yes', 'no'):
            raise ValueError(f'Invalid RewardKit workflow entry: {name}')
        reason = json.loads(entry['reasoning'], object_pairs_hook=unique_object)
        if not isinstance(reason, dict) or set(reason) != {'decision', 'trace', 'citations', 'limitations'}:
            raise ValueError(f'Invalid structured reason: {name}')
        decision = reason['decision']
        if decision not in ('pass', 'fail', 'unknown') or entry['score'] != ('yes' if decision == 'pass' else 'no'):
            raise ValueError(f'Inconsistent workflow decision: {name}')
        if not isinstance(reason['trace'], str) or not reason['trace'].strip():
            raise ValueError(f'Missing causal trace: {name}')
        if not isinstance(reason['limitations'], list) or any(not isinstance(item, str) or not item.strip() for item in reason['limitations']):
            raise ValueError(f'Invalid limitations: {name}')
        if decision == 'unknown' and not reason['limitations']:
            raise ValueError(f'Unknown decision needs an evidence limit: {name}')
        if not isinstance(reason['citations'], list) or not reason['citations']:
            raise ValueError(f'Missing citations: {name}')
        for cite in reason['citations']:
            if (not isinstance(cite, dict) or set(cite) != {'path', 'start_line', 'end_line'}
                or cite['path'] not in allowed or type(cite['start_line']) is not int
                or type(cite['end_line']) is not int or not 1 <= cite['start_line'] <= cite['end_line'] <= allowed[cite['path']]):
                raise ValueError(f'Invalid citation: {name}')
        if not any(not c['path'].startswith('public-contracts/') and Path(c['path']).suffix in {'.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.mts', '.cts', '.html'} for c in reason['citations']):
            raise ValueError(f'Missing application source citation: {name}')
        decisions[name] = reason
    guard = reply['guard']
    if (not isinstance(guard, dict) or set(guard) != {'score', 'reasoning'} or guard['score'] not in ('yes', 'no')
        or not isinstance(guard['reasoning'], str) or not guard['reasoning'].strip()):
        raise ValueError('Invalid guard reply')
    return decisions


def install_completion_boundary(output, manifest, completion=None):
    previous = litellm.acompletion
    original = completion or previous
    original_call = judges._arun_llm_call
    called = False

    async def bounded(**kwargs):
        nonlocal called
        if called:
            raise RuntimeError('This verifier permits one judge request; automatic retries are disabled.')
        called = True
        kwargs.update(max_tokens=MAX_OUTPUT_TOKENS, num_retries=0, max_retries=0)
        if kwargs['model'] != 'anthropic/claude-opus-5-5' or kwargs['reasoning_effort'] != 'high':
            raise ValueError('Voting-page requires Opus 5.5 at high effort.')
        if 'api_key' in kwargs:
            raise ValueError('Judge credentials must use ANTHROPIC_API_KEY, not inline or subscription credentials.')
        if len(json.dumps(kwargs, ensure_ascii=False).encode()) > MAX_REQUEST_BYTES:
            raise ValueError('RewardKit request exceeds the input limit.')
        (output / 'rewardkit-request.json').write_text(json.dumps(kwargs, indent=2) + '\n')
        response = await original(**kwargs)
        (output / 'judge-response.json').write_text(response.model_dump_json(indent=2) + '\n')
        try:
            if response.choices[0].finish_reason != 'stop':
                raise ValueError('Judge response did not finish normally.')
            decisions = validate_reply(response.choices[0].message.content, manifest)
            (output / 'source-decisions.json').write_text(json.dumps(decisions, indent=2) + '\n')
            if any(item['decision'] == 'unknown' for item in decisions.values()):
                raise ValueError('Judge could not determine every workflow; see source-decisions.json.')
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            raise InvalidJudgeResponse(str(error), response) from error
        return response

    async def recorded_call(judge, criteria, weights, *args, **kwargs):
        try:
            return await original_call(judge, criteria, weights, *args, **kwargs)
        except Exception as error:
            response = error.response if isinstance(error, InvalidJudgeResponse) else None
            return JudgeResult(
                scores=[Score(name=criterion.name, value=0.0, raw=None,
                    weight=weights[index] if weights else 1.0, error=str(error),
                    description=criterion.description, id=criterion.id)
                    for index, criterion in enumerate(criteria)],
                output=response.model_dump_json() if response is not None else '',
                warnings=[],
                usage=judges._llm_usage(response, judge.model) if response is not None else {},
            )

    litellm.acompletion = bounded
    judges._arun_llm_call = recorded_call

    def restore():
        litellm.acompletion = previous
        judges._arun_llm_call = original_call
    return restore


def main():
    tests = Path(sys.argv[1] if len(sys.argv) > 1 else '/tests')
    output = Path(os.environ.get('REWARD_OUTPUT', '/logs/verifier/reward.json'))
    workspace = Path(os.environ.get('REWARD_WORKSPACE', '/workspace'))
    for name in (output.name, 'reward.txt', 'reward-details.json', 'judge-response.json', 'source-decisions.json', 'rewardkit-request.json'):
        (output.parent / name).unlink(missing_ok=True)
    if not (tests / 'judge.toml').exists():
        run(tests, workspace=workspace, output=output)
        return
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise RuntimeError('The source judge needs ANTHROPIC_API_KEY. Use the repository free check for free validation.')
    manifest = json.loads((output.parent / 'source-manifest.json').read_text())
    restore = install_completion_boundary(output.parent, manifest)
    try:
        run(tests, workspace=workspace, output=output)
        details = json.loads(output.with_name('reward-details.json').read_text())
        def errors(value):
            if isinstance(value, dict):
                return bool(value.get('error')) or any(errors(child) for child in value.values())
            return isinstance(value, list) and any(errors(child) for child in value)
        if errors(details):
            raise RuntimeError('RewardKit reported a verifier error; see reward-details.json.')
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    finally:
        restore()


if __name__ == '__main__':
    main()
