# Empty return data escapes try/catch

Check whether return-data decoding outside catch lets an EOA notification hook block liquidation.
The fixed-form target is `no`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a lending market compiled with Solidity 0.8.30. Borrowers may register a notification hook, and liquidation calls it inside try/catch so that a broken hook cannot block liquidation.
>
> ```solidity
> function liquidate(address borrower) external {
>     uint256 d = debt[borrower];
>     delete debt[borrower];
>     address hook = hookOf[borrower];
>     if (hook != address(0)) {
>         try IHook(hook).onLiquidation(borrower, d) returns (bytes4) {} catch {}
>     }
>     // seize collateral, pay liquidator
> }
> ```
>
> A borrower calls `setHook` with the address of their own EOA. Does `liquidate(borrower)` succeed? Answer yes or no, then explain in one sentence.

## What it touches

The EVM call to an EOA succeeds and returns no bytes.
Decoding the expected bytes4 fails in the calling contract, outside the catch clause.
The revert restores the deleted debt and stops liquidation.
A hook that reverts during its own call follows the catch path instead.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `eoa_hook_reverts_liquidation` | The reply opens with `no` and gives no explicit alternative or revised target | Audits |

## Why it matters

A borrower-controlled hook can block liquidation even when the source wraps the call in try/catch.
[Solidity's try/catch documentation](https://docs.soliditylang.org/en/v0.8.30/control-structures.html#try-catch) distinguishes callee failures from caller-side decoding failures.
This task claims no named loss incident.

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
| Opus 5.5 | right | right | right | 72 | `f43ec8b728278954655527cf872db9a269f55060a7371e5e1307a0c57d15501d` |
| GPT-6.1-sol | right | right | right | 75 | `b43ab1c347bdd2f3f3239ee2d048213e95b0dee162cbb1d89cca3f04535431b4` |
| Kimi K3.1 Pro | miss | miss | right | 74 | `6b63f33772f469f41b21bee11f1d60c25a1917c5e5e645d72e8d5a2c9bea0127` |
| GLM 5.3 | miss | miss | right | 77 | `5f606d7bfbc34b1c13750629433e511578586e90746a687a4ffc9d711a315f3e` |

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
