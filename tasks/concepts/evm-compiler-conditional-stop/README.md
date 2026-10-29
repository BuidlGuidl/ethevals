# An inlined conditional STOP preserves storage

Check whether an inlined helper avoids Solidity 0.8.16 storage-write removal before conditional STOP.
The fixed-form target is `yes`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> Can this vault safely assume its first storage write survives `save(true)` when compiled with Solidity 0.8.16 and optimized via-IR?
> ```solidity
> uint256 public saved;
> function save(bool finish) external {
>     saved = 1;
>     finishEarly(finish);
>     saved = 2;
> }
> function finishEarly(bool finish) internal {
>     if (finish) { assembly { stop() } }
> }
> ```
> Assume `saved` starts at zero. Answer yes or no, then explain in one sentence.

## What it touches

The standard optimized via-IR pipeline inlines this small helper.
The generated code keeps saved = 1 before the conditional STOP.
The affected compiler version alone does not establish that this source triggers the storage-write-removal bug.
With finish false, execution reaches saved = 2.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `inlined_stop_preserves_write` | The reply opens with `yes` and gives no explicit alternative or revised target | Audits |

## Why it matters

A compiler advisory can cause a false finding when its triggering conditions do not hold.
[Solidity's disclosure](https://www.soliditylang.org/blog/2022/09/08/storage-write-removal-before-conditional-termination/#which-contracts-are-affected) includes an unaffected example whose helper gets inlined.
This question uses the standard optimizer sequence; it does not claim the result for custom Yul sequences.

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
| Opus 5.5 | miss | miss | miss | 84 | `6835800a84bae10d7f9e71d4897ea5256ba041da9d2c0b3921b0a88d3ee29ff8` |
| GPT-6.1-sol | miss | miss | miss | 85 | `0dcde5479240286de85d8da7cba816401a42590999b42a117ecd458df9cd3591` |
| Kimi K3.1 Pro | miss | right | miss | 86 | `18fefe9fd6dcf30f5a1b7343e8fe0b7d79bb16cd4cec4026ee47c78da07c3958` |
| GLM 5.3 | right | miss | right | 87 | `53fc5355e45d6e9843c3cf9b10790b43ee47ef594f945cb250cc3f0591da1ddd` |

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

The early `evm.md` draft gave the wrong target, no. `factcheck-c.md` corrected it to yes before this screening.
The screened instruction stayed unchanged. The target here follows the corrected screened answer and the inlining proof.
