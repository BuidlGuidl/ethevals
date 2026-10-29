# The caller suffix in patched OpenZeppelin Multicall

Check whether OpenZeppelin 5.4 Multicall permits a forged inner ERC-2771 caller suffix.
The fixed-form target is `no`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a treasury that inherits OpenZeppelin Contracts 5.4 `ERC2771Context` and `Multicall`, trusts OpenZeppelin's `ERC2771Forwarder`, and guards `payout()` with `require(_msgSender() == owner)`. A stranger signs a valid forward request to the treasury whose data is `multicall([abi.encodePacked(payout.selector, owner)])`, so the only batched item ends with the owner's 20-byte address, and relays it through the forwarder. Does `payout()` run? Answer yes or no, then explain in one sentence.

## What it touches

Patched Multicall appends the real forwarder's caller context to every delegated item.
The stranger's address follows the forged owner suffix, so `_msgSender()` returns the stranger.
The owner check fails even though the stranger signed a valid forward request.
The old 4.9.1 Multicall lacks this protection.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `forged_suffix_cannot_pay` | The reply opens with `no` and gives no explicit alternative or revised target | Audits |

## Why it matters

[OpenZeppelin's December 2023 disclosure](https://www.openzeppelin.com/news/arbitrary-address-spoofing-vulnerability-erc2771context-multicall-public-disclosure) reports the older address-spoofing pattern and losses of 84.59 ETH and 17,394 USDC.
This tests whether a stranger can pretend to be the owner when a contract runs several calls together.
Those losses concern the older pattern, not patched 5.x behavior.
[Multicall 5.4.0](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.4.0/contracts/utils/Multicall.sol) appends the authenticated context.
The protection began in 4.9.4 and 5.0.1 and remains in 5.7.0.

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
| Opus 5.5 | right | right | right | 69 | `d0b2140ff4c4f51c8aefa4410873430f42bf0b60bec5cd1a65367376100cf850` |
| GPT-6.1-sol | right | right | right | 70 | `49673aed1c65c7407e51d7c5e729567894c8dffe5a8b237ca02c9c9e63db2c87` |
| Kimi K3.1 Pro | miss | miss | miss | 71 | `c1af79319345aac95d5b81a1e79e7a5c3696f7bcad5e37adaa01bd7dba994a73` |
| GLM 5.3 | cut off | cut off | cut off | 73 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

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
The proof includes the required OpenZeppelin 5.4.0 and 4.9.1 source files under `dependencies/`.
The source files match the screened proof's pinned npm packages byte for byte.
The proof passed again on 2026-10-30, including these controls:

```text
[PASS] testForgedInnerSuffixIgnoredOZ54() (gas: 1285528)
[PASS] testOwnerSignedMulticallPays() (gas: 1306357)
[PASS] testStrangerRequestVerifies() (gas: 1256193)
[PASS] testControlOZ491SpoofWorks() (gas: 529928)
```
