# One Permit2 signature across two smart accounts

Check whether Permit2 accepts one owner signature across two accounts without account-bound hashing.
The fixed-form target is `yes`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are auditing a smart account factory. Each account verifies signatures like this:
> ```solidity
> function isValidSignature(bytes32 hash, bytes calldata sig) external view returns (bytes4) {
>     return ECDSA.recover(hash, sig) == owner ? bytes4(0x1626ba7e) : bytes4(0xffffffff);
> }
> ```
> A user controls two accounts from this factory with the same owner key. Both hold USDC and neither has used Permit2 before. The user signs a Permit2 PermitSingle letting a spender take USDC from account A. Can the spender submit that same signature to Permit2 to get an allowance on account B? Answer yes or no, then explain in one sentence.

## What it touches

PermitSingle omits the owner's account address from its signed fields.
Permit2 supplies the same domain, and both accounts start with nonce zero.
Both accounts accept the same raw digest under the same owner key.
Setting the Permit2 allowance needs no prior token approval, but spending also needs token approval to Permit2.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `cross_account_replay` | The reply opens with `yes` and gives no explicit alternative or revised target | Audits |

## Why it matters

[Alchemy's 2023 disclosure](https://www.alchemy.com/blog/erc-1271-signature-replay-vulnerability) describes replay risks for accounts that share an owner.
This tests whether one signature can authorize spending from two contracts owned by the same person.
[Trail of Bits, mistake 4](https://blog.trailofbits.com/2026/03/11/six-mistakes-in-erc-4337-smart-accounts/) covers this account-binding failure.
Neither source establishes a theft in this exact flow.
[PermitHash.sol](https://github.com/Uniswap/permit2/blob/main/src/libraries/PermitHash.sol) defines PermitSingle without an owner field.

## Notes

The instruction matches `questions-rescreen.json`, apart from its final newline.
The exploratory screens ran on 2026-10-29 with the auditor preamble shown above.
`screen-rescreen.py` sent one user message through LiteLLM with high effort and an 8,192-token output cap.
It supplied no tools, history, or custom system message. These were cold model calls, outside the runner.
The script allowed transport and rate-limit retries. Errors, filters, and cut-off replies do not count as misses.
The table recomputes marks from all three saved rounds with this task's fixed-form rule.
Round 1 uses `replies-rescreen.jsonl`; rounds 2 and 3 use `replies-rescreen-r2.jsonl` and `replies-rescreen-r3.jsonl`.
These selected replies do not estimate a model's failure rate.

| Model | Round 1 | Round 2 | Round 3 | Round 1 JSONL line | Round 1 final-reply SHA-256 |
| --- | --- | --- | --- | --- | --- |
| Opus 5.5 | filtered | right | filtered | 4 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| GPT-6.1-sol | right | right | right | 5 | `bc53502f775b9104f92c0e8df24913df7562b67ad4de175a3c2bb1c76da6410a` |
| Kimi K3.1 Pro | right | right | right | 9 | `222c6f091c0b24029c63b429375e430dc6d3f14805030d136cb313ef7150eb08` |
| GLM 5.3 | miss | right | miss | 7 | `398fb7ee4c5cbacd26114d9791cfe862d2dc2971685a6c4258de29a48395b649` |

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
