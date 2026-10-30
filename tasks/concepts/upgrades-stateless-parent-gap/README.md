# A stateless parent changes proxy storage

Check whether adding OpenZeppelin MulticallUpgradeable 4.9.6 moves an existing balance mapping.
The fixed-form target is `0`.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> You are reviewing a V2 upgrade of a UUPS vault built on OpenZeppelin Contracts Upgradeable 4.9.6.
>
> ```solidity
> contract VaultV1 is Initializable, OwnableUpgradeable, UUPSUpgradeable {
>     mapping(address => uint256) public balanceOf;
>     // ...
> }
>
> contract VaultV2 is Initializable, OwnableUpgradeable, UUPSUpgradeable, MulticallUpgradeable {
>     mapping(address => uint256) public balanceOf;
>     // ... same functions as V1
> }
> ```
>
> V2 only appends `MulticallUpgradeable` so users can batch calls. Alice's V1 balance is 100. The owner upgrades the proxy to V2 with no migration. What does `balanceOf(alice)` return afterwards? Answer with the number only.

## What it touches

MulticallUpgradeable 4.9.6 reserves a 50-slot storage gap despite having no application variables.
Adding this parent moves balanceOf from slot 201 to slot 251 in the shown hierarchy.
The old mapping entries remain in storage, but the new getter reads the new mapping location.
The owner slot stays in place.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `shifted_balance_reads_zero` | The reply opens with `0` and gives no explicit alternative or revised target | Audits |

## Why it matters

Appending a parent can move a child's storage even when the parent looks stateless.
[MulticallUpgradeable 4.9.6](https://github.com/OpenZeppelin/openzeppelin-contracts-upgradeable/blob/v4.9.6/contracts/utils/MulticallUpgradeable.sol) declares the gap.
[OpenZeppelin's storage-gap guide](https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps) explains its purpose.
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
| Opus 5.5 | right | right | right | 65 | `099179ef1d7c2b85d540c14f94b4bd5b10bc52e7c53f0bd8b6e40c5d30d14ad1` |
| GPT-6.1-sol | right | right | right | 66 | `5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9` |
| Kimi K3.1 Pro | miss | miss | miss | 68 | `ad57366865126e55649ecb23ae1d48887544976efea46a48eb5d85a6eeb4d306` |
| GLM 5.3 | miss | miss | error: truncated | 67 | `0e5f750fa3d06f011e5f11db59b66f9eb8d10a13ff457db069dd45807fc71090` |

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
