# Legacy state-variable initialization order

Check whether a derived initializer reads ownership before the base constructor sets it in legacy Solidity.
The fixed-form target is `zero address`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing this fee vault before launch. It is compiled with Solidity 0.8.30, optimizer on, legacy pipeline (no via-IR). `Ownable` is OpenZeppelin Contracts 5.4.
>
> ```solidity
> contract FeeVault is Ownable {
>     address public feeRecipient = owner();
>
>     constructor() Ownable(msg.sender) {}
>
>     function collectFees() external {
>         payable(feeRecipient).transfer(address(this).balance);
>     }
> }
> ```
>
> Alice's EOA deploys it. Right after deployment, what does `feeRecipient()` return? Answer Alice's address or the zero address, then explain in one sentence.

## What it touches

The legacy pipeline evaluates state-variable initializers across the hierarchy before it runs constructors.
The feeRecipient initializer therefore reads zero from owner().
Ownable later sets the owner, but that write does not update feeRecipient.
The via-IR pipeline uses a different order.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `zero_fee_recipient` | The reply opens with `zero address` and gives no explicit alternative or revised target | Audits |

## Why it matters

A recipient captured before its base constructor runs can send later fees to the zero address.
[Solidity's code-generation comparison](https://docs.soliditylang.org/en/v0.8.30/ir-breaking-changes.html#semantic-only-changes) documents this initialization-order difference.
This task claims no production loss incident.

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
| Opus 5.5 | right | right | right | 48 | `55a0883a0b9c9c2f745fd355835db426b63b9ea6317068c281e95b8f8ae3322d` |
| GPT-6.1-sol | right | right | right | 50 | `8c51deb239ced8a87165115c5e196408f1778776bd329068c89aece2ad4128af` |
| Kimi K3.1 Pro | miss | miss | miss | 52 | `7e4522bc35e50dcdc2bfcfac45480adf724b791eacdb99e4fa22ff2b7a168b6c` |
| GLM 5.3 | miss | miss | miss | 51 | `23ac23f7fefb618938a5aa22e508f1c0605a95534f5c3aeb69f91cad895b06d4` |

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
