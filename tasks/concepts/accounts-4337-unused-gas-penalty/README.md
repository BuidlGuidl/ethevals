# A paymaster pays the unused-gas penalty

Check whether an EntryPoint v0.7 paymaster pays a penalty for excessive unused execution gas.
The fixed-form target is `no`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a verifying paymaster for EntryPoint v0.7. It signs any user operation from the app's users with callGasLimit up to 5,000,000 and pays from its EntryPoint deposit. A bundler can register as an app user, submits its own operations with callGasLimit set to 5,000,000 each time, and keeps the fees. Is the paymaster charged only for the gas each operation actually used? Answer yes or no, then explain in one sentence.

## What it touches

EntryPoint v0.7 charges a 10% penalty on unused execution and postOp gas limits.
The penalty comes from the paymaster's deposit and goes to the bundler's beneficiary.
EntryPoint v0.8 adds a 40,000-gas threshold, but a five-million limit still permits this fee drain.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `unused_gas_penalty_charged` | The reply opens with `no` and gives no explicit alternative or revised target | Audits |

## Why it matters

[Osec's SEND paymaster analysis](https://osec.io/blog/2025-12-02-paymasters-evm) describes undercharging for gas penalties and possible bundler profit.
This tests whether a contract that pays users' fees also pays for an excessive unused allowance.
The article says SEND's own bundler contains that risk and reports no realized loss.
[EntryPoint v0.7](https://github.com/eth-infinitism/account-abstraction/blob/v0.7.0/contracts/core/EntryPoint.sol) implements the 10% penalty.
[EntryPoint v0.8](https://github.com/eth-infinitism/account-abstraction/blob/v0.8.0/contracts/core/EntryPoint.sol) adds the threshold.

## Notes

The instruction omits "A typical operation uses about 150,000 gas in execution." at the owner's request.
All three screens used the longer wording in `questions-rescreen.json`.
The table records those earlier replies, not a new screen of the shorter instruction.
The exploratory screens ran on 2026-10-29 with the auditor preamble shown above.
`screen-rescreen.py` sent one user message through LiteLLM with high effort and an 8,192-token output cap.
It supplied no tools, history, or custom system message. These were cold model calls, outside the runner.
The script allowed transport and rate-limit retries. Errors, filters, and cut-off replies do not count as misses.
The table recomputes marks from all three saved rounds with this task's fixed-form rule.
Round 1 uses `replies-rescreen.jsonl`; rounds 2 and 3 use `replies-rescreen-r2.jsonl` and `replies-rescreen-r3.jsonl`.
These selected replies do not estimate a model's failure rate.

| Model | Round 1 | Round 2 | Round 3 | Round 1 JSONL line | Round 1 final-reply SHA-256 |
| --- | --- | --- | --- | --- | --- |
| Opus 5.5 | right | right | right | 1 | `b96b99aa14e5d571b0709e33448e0d32d3365d289656579ed9083a3a24e8bf3c` |
| GPT-6.1-sol | right | right | right | 2 | `e885b7e854b6b21ba647d3e1eaf4cdc28c120f5a72ef6bdf59c931f16c6bd076` |
| Kimi K3.1 Pro | right | right | right | 6 | `770e25caaa0a4be8e5d3f323e22b5a878f7b62ea67a50d3e940edda0d3484766` |
| GLM 5.3 | miss | miss | miss | 3 | `bbfc5e96c0b3e36538682b71484077736cf4770ffa0caeed4231d442d050c8fb` |

The model IDs were `anthropic/claude-opus-5-5`, `openai/gpt-6.1-sol`,
`openrouter/moonshotai/kimi-k3.1-pro`, and `openrouter/z-ai/glm-5.3`.
The source files remain in the local `/tmp/subagents/security-quizzes/` evidence directory.
Input file SHA-256: `41a788ab2220063e600dd1cc777d9cc5d437ebbe6ff5f874d24a84b3bc324e74`.
First-round replies SHA-256: `f2a2ca63fe49273518a5f49f2127bc8d18ef9f431ff488ae48d30a0c3bbad5ac`.

The verifier checks the opening fixed-form target and rejects explicit alternative or revised target forms.
It accepts Markdown around that target and permits an explanation afterward.
It does not judge the explanation or prove that every sentence agrees with the opening answer.
`tests/hand-cases.json` includes real accepted and rejected replies, a hedge, a near miss, and the solution.

The task uses `area = "Audits"`, which [PR #79](https://github.com/BuidlGuidl/ethevals/pull/79) maps to Security.
