# Transient clearing and pending ownership

Check whether a Solidity 0.8.33 via-IR delete-helper collision leaves pending ownership after renunciation.
The fixed-form target is `yes`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing this vault, compiled with Solidity 0.8.33, via-IR, optimizer on, EVM version cancun. `Ownable2Step` is OpenZeppelin Contracts 5.4.
>
> ```solidity
> contract Vault is Ownable2Step {
>     address transient activeCaller;
>
>     constructor() Ownable(msg.sender) {}
>
>     function run() external {
>         activeCaller = msg.sender;
>         // ... work that reads activeCaller ...
>         delete activeCaller;
>     }
> }
> ```
>
> The deployer calls `transferOwnership(bob)`, Bob calls `acceptOwnership()`, and later Bob calls `renounceOwnership()`. Can Bob then call `acceptOwnership()` again and become owner? Answer yes or no, then explain in one sentence.

## What it touches

The transient address and the persistent pending-owner address require clearing helpers for the same value type.
The affected compiler gives those helpers one name and can emit TSTORE for the persistent clear.
Bob remains the pending owner after acceptance and renunciation in this contract.
The legacy pipeline and Solidity 0.8.34 controls clear pending ownership correctly.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `bob_can_reclaim_ownership` | The reply opens with `yes` and gives no explicit alternative or revised target | Audits |

## Why it matters

A compiler error can undo the intended finality of ownership renunciation.
[Solidity's disclosure](https://www.soliditylang.org/blog/2026/02/18/transient-storage-clearing-helper-collision-bug/) covers versions 0.8.28 through 0.8.33 and the same-type clearing condition.
It records the fix in 0.8.34.
This task claims no public exploit of this vault.

## Notes

The instruction matches `questions-rescreen.json` byte for byte, apart from its final newline.
The exploratory screening ran on 2026-10-29 with the auditor preamble shown above.
`screen-rescreen.py` sent one user message through LiteLLM with high effort and an 8,192-token output cap.
It supplied no tools, history, or custom system message. These were cold model calls, outside the runner.
The script allowed transport and rate-limit retries. Errors, filters, and truncated replies do not count as misses.
Round 1 records the marks used by `grades-rescreen.json` to select this question.
Rounds 2 and 3 record the later final-form verifier replays, with errors kept separate.
Two later rounds also exist, under `replies-rescreen-r2.jsonl` and `replies-rescreen-r3.jsonl`.
Their outcomes can differ; this table is neither a pooled score nor a claim of repeatable failure.

| Model | Round 1 | Round 2 | Round 3 | Round 1 JSONL line | Round 1 final-reply SHA-256 |
| --- | --- | --- | --- | --- | --- |
| Opus 5.5 | error: content filter | right | right | 60 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| GPT-6.1-sol | miss | right | right | 62 | `9395c3a4c2d5da08d25ece11a9e66106c95c9d955ee16e6f56e45a39e5aac83a` |
| Kimi K3.1 Pro | miss | miss | miss | 64 | `431ae4553d9ffee774067caacd1e88d8450540b84581346d46cde51112f95b5b` |
| GLM 5.3 | miss | miss | miss | 63 | `dc0b0131c362ceed9f2da3ebc79bf13c1eedb5e1ba78be77b03deb724f46e074` |

The model IDs were `anthropic/claude-opus-5-5`, `openai/gpt-6.1-sol`,
`openrouter/moonshotai/kimi-k3.1-pro`, and `openrouter/z-ai/glm-5.3`.
The source files remain in the local `/tmp/subagents/security-quizzes/` evidence directory; they are not repository artifacts.
Input file SHA-256: `41a788ab2220063e600dd1cc777d9cc5d437ebbe6ff5f874d24a84b3bc324e74`.
First-round replies SHA-256: `f2a2ca63fe49273518a5f49f2127bc8d18ef9f431ff488ae48d30a0c3bbad5ac`.

The verifier checks the opening fixed-form target and rejects explicit alternative or revised target forms.
It accepts Markdown around that target and permits an explanation afterward.
It does not judge the explanation or prove that every sentence agrees with the opening answer.
`tests/hand-cases.json` records accepted and rejected forms, including the solution.
All three rounds of saved final replies were also replayed through RewardKit during implementation.

The task uses `area = "Audits"`. The security domain mapping depends on [PR #79](https://github.com/BuidlGuidl/ethevals/pull/79).
That PR derives domains from areas; this task adds no domain field or site code.
