# The outer domain in ERC-7739 TypedDataSign

Identify the outer domain separator in an ERC-7739 TypedDataSign digest.
The fixed-form target is `dapp`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a smart account's ERC-7739 isValidSignature. A dapp asks the account's owner to sign an EIP-712 Order under the dapp's own domain, and the account verifies it through the TypedDataSign workflow. In the final digest the owner's key signs, which domain separator comes right after the 0x1901 prefix: the dapp's or the account's? Answer dapp or account, then explain in one sentence.

## What it touches

TypedDataSign keeps the dapp's domain separator immediately after `0x1901`.
The account's name, version, chain ID, address, and salt enter the inner signed structure.
PersonalSign uses the account's domain in the outer position instead.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `dapp_domain_outside` | The reply opens with `dapp`, `app` or `application` and gives no explicit alternative or revised target | Audits |

## Why it matters

[Alchemy's 2023 disclosure](https://www.alchemy.com/blog/erc-1271-signature-replay-vulnerability) describes cross-account signature replay.
This tests which contract's identity surrounds the signature when one contract checks a signature for another.
[ERC-7739](https://eips.ethereum.org/EIPS/eip-7739) specifies the later TypedDataSign format and addresses readable defensive rehashing.
The disclosure does not establish that later format or report a loss from it.

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
| Opus 5.5 | right | right | right | 8 | `0631dd18e1607e61976f765ee3359bca483eebc543fb3d920450be49dae80945` |
| GPT-6.1-sol | right | right | right | 10 | `982e1a0624eed248754bf2406382fe2943321e27aaa78f57d78a662f34a5bfad` |
| Kimi K3.1 Pro | miss | miss | miss | 11 | `51d610e5ffc94e025b494498021f1551b436d44fa31622fe87d32013cd584edb` |
| GLM 5.3 | miss | miss | miss | 16 | `244fed0b277957190664c160685a044ba519a00221100d536a3ab807bd760884` |

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
