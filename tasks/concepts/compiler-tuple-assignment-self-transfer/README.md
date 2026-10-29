# Tuple assignment on a self-transfer

Check the final balance after aliased mapping entries receive a tuple assignment in Solidity 0.8.30.
The fixed-form target is `60`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing this token, compiled with Solidity 0.8.30, optimizer on.
>
> ```solidity
> mapping(address => uint256) public balanceOf;
>
> function transfer(address to, uint256 amount) external {
>     uint256 fromBal = balanceOf[msg.sender];
>     uint256 toBal = balanceOf[to];
>     require(fromBal >= amount, "balance");
>     (balanceOf[msg.sender], balanceOf[to]) = (fromBal - amount, toBal + amount);
> }
> ```
>
> Alice holds 100 tokens and calls `transfer(alice, 40)`, sending to herself. What is `balanceOf(alice)` afterwards? Answer with the number only.

## What it touches

Both cached balances start at 100, so the right-hand tuple contains 60 and 140.
Solidity 0.8.30 writes the right component first and the left component last.
Both destinations name Alice's mapping entry, so the final write leaves 60.
Both legacy and via-IR compilation give this result with the optimizer enabled.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `self_transfer_balance_60` | The reply opens with `60` and gives no explicit alternative or revised target | Audits |

## Why it matters

Aliased writes can destroy balances as well as inflate them.
[Solidity's assignment documentation](https://docs.soliditylang.org/en/v0.8.30/control-structures.html#destructuring-assignments-and-returning-multiple-values) does not promise a component-write order.
The target rests on execution with the named compiler, rather than a guarantee for future compilers.
[Solidity 0.8.30 source](https://github.com/ethereum/solidity/blob/v0.8.30/libsolidity/codegen/LValue.cpp#L589) also shows the legacy generator writing components from right to left.
This task claims no loss incident for this exact tuple form.

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
| Opus 5.5 | right | right | right | 56 | `9f82a38b5fd6bb7ed1e9f2374a3fbb74883dc9199d2d957837277c86a2a6ffe6` |
| GPT-6.1-sol | right | right | right | 57 | `39fa9ec190eee7b6f4dff1100d6343e10918d044c75eac8f9e9a2596173f80c9` |
| Kimi K3.1 Pro | miss | miss | miss | 58 | `dbae772db29058a88f9bd830e957c695347c41b6162a7eb9a9ea13def34be56b` |
| GLM 5.3 | miss | miss | miss | 59 | `b663eb693b74c6b5e66ebc4145539f14052f3a14160c3be956b668b4cb818067` |

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
