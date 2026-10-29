# ERC-7739 TypedDataSign domain

Check which domain separator ERC-7739 TypedDataSign puts outside the nested struct.
The fixed-form target is `dapp`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a smart account's ERC-7739 isValidSignature. A dapp asks the account's owner to sign an EIP-712 Order under the dapp's own domain, and the account verifies it through the TypedDataSign workflow. In the final digest the owner's key signs, which domain separator comes right after the 0x1901 prefix: the dapp's or the account's? Answer dapp or account, then explain in one sentence.

## What it touches

TypedDataSign keeps the dapp's domain separator after `0x1901`.
The account's domain fields belong inside the nested struct.
PersonalSign uses a different outer domain, so its rule does not answer this question.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `dapp_domain` | The reply opens with `dapp` and gives no explicit alternative or revised target | Audits |

## Why it matters

Putting the account domain in the outer position produces a different digest and rejects the owner's signature.
[ERC-7739](https://eips.ethereum.org/EIPS/eip-7739#typeddatasign-workflow) defines the two workflows.
The ERC remains a draft; this question uses its TypedDataSign formula as screened on 2026-10-29.

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
| Opus 5.5 | right | right | right | 8 | `0631dd18e1607e61976f765ee3359bca483eebc543fb3d920450be49dae80945` |
| GPT-6.1-sol | right | right | right | 10 | `982e1a0624eed248754bf2406382fe2943321e27aaa78f57d78a662f34a5bfad` |
| Kimi K3.1 Pro | miss | miss | miss | 11 | `51d610e5ffc94e025b494498021f1551b436d44fa31622fe87d32013cd584edb` |
| GLM 5.3 | miss | miss | miss | 16 | `244fed0b277957190664c160685a044ba519a00221100d536a3ab807bd760884` |

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
