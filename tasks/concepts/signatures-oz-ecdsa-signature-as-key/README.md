# Changing the bytes of an OpenZeppelin signature

Check whether OpenZeppelin 5.x accepts another encoding of one withdrawal-voucher signature.
The fixed-form target is `no`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a vault's withdrawal-voucher flow before launch. An offchain service signs vouchers with one EOA key, `signer`.
>
> ```solidity
> using ECDSA for bytes32; // OpenZeppelin Contracts 5.x
> mapping(bytes32 => bool) public used;
>
> function claim(uint256 amount, bytes calldata sig) external {
>     bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(CLAIM_TYPEHASH, msg.sender, amount)));
>     require(digest.recover(sig) == signer, "bad sig");
>     require(!used[keccak256(sig)], "used");
>     used[keccak256(sig)] = true;
>     token.transfer(msg.sender, amount);
> }
> ```
>
> Can a user holding one valid voucher claim it twice by changing the signature bytes? Answer yes or no, then explain in one sentence.

## What it touches

OpenZeppelin 5.x's `recover(bytes)` overload accepts 65-byte signatures and rejects high-s values.
It rejects both the EIP-2098 compact encoding and the high-s twin of the supplied signature.
This claim concerns changing one signature's bytes, not a signer issuing another signature for the same message.
Keying replay protection by the message digest also covers that separate risk.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `signature_reencoding_rejected` | The reply opens with `no` and gives no explicit alternative or revised target | Audits |

## Why it matters

[OpenZeppelin advisory GHSA-4h98-2769-gh6h](https://github.com/OpenZeppelin/openzeppelin-contracts/security/advisories/GHSA-4h98-2769-gh6h) describes bypassing replay protection keyed by signature bytes.
This tests whether a user can change one signature's form to claim the same payment twice.
The advisory dates to August 10, 2022, affects versions 4.1.0 through 4.7.2, and records the fix in 4.7.3.
It is a disclosure, not evidence of an exploit.
[OpenZeppelin 5.7.0 ECDSA.sol](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/contracts/utils/cryptography/ECDSA.sol) retains these checks.
Its notice says version 6.0 will remove the bytes overload's length restriction.

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
| Opus 5.5 | right | right | right | 17 | `fa0fd969252718aae15d25ea440c5e08196acd8bd98ba743de5afd17fa1f9712` |
| GPT-6.1-sol | right | right | right | 18 | `a1a871ee0489bce8ae95187cb6c288148b3ac95158d646fad90a78ce643199b3` |
| Kimi K3.1 Pro | miss | right | miss | 19 | `537de814de25d6ff5656ddf1e88fdf7d96835de7f8d99d9be81b0738502339e3` |
| GLM 5.3 | right | miss | miss | 20 | `658b9f1616aad4204eea9679412d3a41d80155e59874cfa1af7a2dae290914cd` |

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
