# Deleting a memory byte clears the recipient

Check whether Solidity 0.8.30 legacy byte deletion erases a packed payment recipient.
The fixed-form target is `zero address`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a bridge's message builder, compiled with Solidity 0.8.30, optimizer on, legacy pipeline (no via-IR).
>
> ```solidity
> function build(address recipient, uint256 amount)
>     external pure returns (bytes memory payload)
> {
>     payload = abi.encodePacked(uint8(1), recipient, amount); // flag, recipient, amount
>     delete payload[0];                                      // clear the flag
> }
> ```
>
> The relayer reads the recipient from bytes 1 to 20 of `payload`. After `build(alice, 5 ether)`, which recipient does the payload carry? Answer Alice's address or the zero address, then explain in one sentence.

## What it touches

The affected legacy code generator clears a memory bytes element with a 32-byte MSTORE.
Deleting the flag therefore clears the adjacent recipient as well.
The remaining amount bytes still encode 5 ether.
The bug affects the legacy pipeline through 0.8.36. Solidity 0.8.37 fixes it, and via-IR is unaffected.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `zero_payload_recipient` | The reply opens with `zero address` and gives no explicit alternative or revised target | Audits |

## Why it matters

[Solidity's September 10, 2026 disclosure](https://www.soliditylang.org/blog/2026/09/10/memory-byte-array-element-delete-clears-whole-word-bug/) describes the whole-word overwrite and its 0.8.37 fix.
This tests whether clearing one byte with an older compiler can also erase the payment recipient beside it.
The disclosure says no deployed contract is known to be affected.
[The released bugs list](https://github.com/argotorg/solidity/blob/v0.8.38/docs/bugs.json) records the affected pipeline and compiler range.
Solidity 0.8.38 preserves Alice's address, while this instruction pins the affected 0.8.30 compiler.

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
| Opus 5.5 | filtered | miss | miss | 80 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| GPT-6.1-sol | right | right | right | 81 | `581dbf6795835f65cbf9e5c7677459a4d1f9819f5d449f35210c91555a529e1f` |
| Kimi K3.1 Pro | miss | miss | miss | 82 | `a67619e62ac69f497c2ed5885b8368d443795da4cecebc5275dc7861aca580bf` |
| GLM 5.3 | cut off | cut off | cut off | 83 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

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

`solution/proof/` keeps the Foundry proof and its controls outside the agent environment.
Run `cd solution/proof && forge test` from this task folder.
Run `FOUNDRY_PROFILE=viair forge test` and `FOUNDRY_PROFILE=fixed forge test` there for the controls.
The proof passed again on 2026-10-30:

```text
default: [PASS] testDeleteZeroesRecipient() (gas: 106614)
viair:   [PASS] testDeleteKeepsRecipient() (gas: 92175)
fixed:   [PASS] testDeleteKeepsRecipient() (gas: 106615)
```
