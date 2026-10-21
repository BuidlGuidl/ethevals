# Introduction

## What is an eval?

An eval is a prompt for an agent or a bare model, plus the checks that decide whether it did it right.
You write the prompt, what the agent starts with, and the checks, all in one folder.

## The eval folder

Every eval belongs to one of four pillars:

- `concepts`
- `transactions`
- `building`
- `security`

An eval lives in `evals/<pillar_name>/<eval_name>/`, and `<pillar_name>/<eval_name>` is its ID:

```text
evals/
└── <pillar_name>/
    └── <eval_name>/
        ├── eval.yaml     required: the prompt, the modes, and the chain
        ├── workspace/    optional: the files the agent starts with
        ├── scorer/       required: the checks
        ├── setup/        required if chain is needed: setup.s.sol, which prepares the chain before the agent starts
        ├── solution/     required if tests or a chain is needed: the reference solution, which proves the checks can pass
        └── compose.yaml  optional: extra services the agent can call, like a database
```

Let's look at each piece:

### `eval.yaml`

`eval.yaml` is the eval's entry point. It holds the prompt given to the agent or model being tested, and how the eval runs. It takes these keys:

| Key          | Required | Holds                                                            |
| ------------ | -------- | ---------------------------------------------------------------- |
| `prompt`     | yes      | the message / task the agent or model which is being tested gets |
| `motivation` | yes      | why the eval exists, shown on the website                        |
| `modes`      | yes      | any of `vanilla`, `internet`, and `skills`                       |
| `chain`      | no       | `anvil`, or a fork like `{fork: mainnet, block: 1}`       |
| `choices`    | no       | 2 to 26 answers for a multiple-choice quiz                       |

`prompt`: write it the way a real person would send it, the agent must not know it is being tested.

`modes` picks how the eval runs:

- `vanilla`: sends the prompt to a bare model with no tools. Use it only for an eval with no chain, no workspace files, and no tests.
- `internet`: runs an agent with the web, a shell, the workspace, and the chain.
- `skills`: `internet` plus the [skills pack](../skills/README.md).

### `workspace/`

`workspace/` is the folder the agent works in. Anything you put here is waiting for the agent when it starts, like a Foundry project to build on, or a `AGENTS.md` that adds detail to the `prompt`.

If the eval has a chain, `setup` dir writes `chain.json` here before the agent starts. That's our convention for telling the agent about the chain it works on. Since setup writes it each time the eval runs, you don't have to fix contract addresses or the agent's wallet ahead of time.

### `scorer/`

`scorer/` holds the checks that decide whether the agent got it right. A check is one pass-or-fail result with a name and a short reason. The agent passes only if every check passes. You pick the checks that fit your eval, and you can use more than one kind:

| File                   | Checks                                           |
| ---------------------- | ------------------------------------------------ |
| `scorer/target.yaml`   | the final reply                                  |
| `scorer/tests/*.t.sol` | the chain, the agent's code, or both, with Forge |
| `scorer/rubric.md`     | the transcript, graded by an LLM                 |

**Target:** A target is the quickest way to write a quiz. You write the answer, and the check compares the reply with it.

<details>
<summary><code>target.yaml</code> keys, multiple choice, and pattern targets</summary>

`target.yaml` takes these keys:

| Key           | Default          | Holds                                      |
| ------------- | ---------------- | ------------------------------------------ |
| `name`        | `answer`         | the check's name                           |
| `target`      | required         | the answer, or a list where any one passes |
| `method`      | `match`          | `match` or `pattern`                       |
| `location`    | `exact`          | `begin`, `end`, `any`, or `exact`          |
| `ignore_case` | `true`           | ignore case when comparing                 |
| `numeric`     | `false`          | compare as numbers                         |
| `pattern`     | none             | the regex for `method: pattern`            |
| `reference`   | the first target | the reply `check` sends                    |

**Multiple choice:** Add `choices` to `eval.yaml` and set `target` to the right letter.
From the test fixture [`wei-per-ether`](../inspect-runner/tests/fixtures/concepts/wei-per-ether):

```yaml
motivation: Check whether a model knows Ethereum's base unit conversion.
prompt: How many wei equal one ether?
choices:
  - "10^6"
  - "10^9"
  - "10^18"
  - "10^24"
modes: [vanilla, internet]
```

```yaml
name: wei_conversion
target: C
```

**Pattern targets:** `method: pattern` pulls the answer out of the reply with a regex group, then compares it with `target`, for example:

```yaml
name: erc_number
method: pattern
pattern: 'ERC-?(\d+)'
target: "20"
reference: "It is ERC-20."
```

</details>

**Tests:** Forge tests check the chain, the agent's code, or both. Each test function is one check.

<details>
<summary>Example test</summary>

```solidity
function test_recipient_balance() public view {  // (1)
    assertEq(recipient.balance, 2 ether, "recipient holds the requested ether");  // (2)
}
```

1. The function name is the check's name.
2. If the assertion fails, its message becomes the reason, like `recipient holds the requested ether: 0 != 2000000000000000000`.

</details>

**Rubric:** A rubric covers what only the transcript shows, like whether the agent verified its work. Each heading is one check.

<details>
<summary>Example rubric</summary>

```markdown
## verified_transfer  <!-- (1) -->

Before reporting success, did the agent confirm on-chain that the transfer landed, for example by reading the transaction receipt or the recipient's token balance?  <!-- (2) -->
```

1. The heading is the check's name.
2. An LLM reads the transcript, answers the question with pass or fail, and writes the reason.

</details>

### `setup/`

`setup/` runs before the agent starts and sets up its world. For example, it can pick the wallet the agent uses, fund it, or deploy the contracts the eval asks about.

Setup scripts are Solidity files, `setup/setup.s.sol`, and we run them with `forge script`. So you can use anything Foundry gives you.

To tell the agent about the chain, like its wallet or a contract address, you write it to `chain.json`. We put that file in the agent's `workspace/`, and your prompt can ask the agent to read it.

We also have a `ChainSetup` helper that your script can extend. It gives you these functions:

- `fund(addr, amount)`: sets the ETH balance of `addr`.
- `chainRecord(name, value)`: adds a field to `chain.json`, which the agent and the tests read.
- `privateRecord(name, value)`: adds a field to `private.json`, which only the tests read.

<details>
<summary>Example <code>setup.s.sol</code></summary>

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";

contract Setup is ChainSetup {
    function run() external {
        Vm.Wallet memory me = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(me.addr, 10 ether);  // (1)
        chainRecord("privateKey", bytes32(me.privateKey));  // (2)
        privateRecord("startBalance", uint256(10 ether));  // (3)
    }
}
```

1. Gives the wallet 10 ETH on the chain.
2. Puts the wallet's key in `chain.json` for the agent.
3. Puts a value in `private.json` that only the tests can read.

</details>

### `compose.yaml`

Add a `compose.yaml` with the services the agent can call, for example:

```yaml
services:
  database:
    image: postgres:17@sha256:d74eeac9a635390a49bc21bd49fccd973de707e2a53a76ac49b552b8712ec46f
    environment:
      POSTGRES_PASSWORD: postgres
    mem_limit: 512m
```

An epoch is one agent or model doing an eval once, in one mode. Here is the lifecycle of an epoch:

```mermaid
flowchart LR
	host["Host: the runner"]
	subgraph chainbox["Chain container"]
		anvil["anvil"]
	end
	subgraph agentbox["Agent container"]
		agent["the agent in workspace/"]
	end
	subgraph scorerbox["Scorer container"]
		tests["scorer/tests/"]
	end
	host -- "Step 1: runs setup.s.sol" --> anvil
	host -- "Step 2: prompt, workspace/, chain.json" --> agent
	agent -- "Step 3: RPC calls" --> anvil
	host -- "Step 4: workspace/, chain.json, private.json" --> tests
	tests -- "reads the chain" --> anvil
```

1. The host runs `setup/setup.s.sol` against the chain. Setup writes `chain.json` and `private.json`.
2. The host copies `workspace/` and `chain.json` into the agent container and sends the prompt.
3. The agent works in `workspace/` and talks to the chain over RPC. It never sees `scorer/`, `solution/`, or `private.json`.
4. When the agent stops, the host copies its `workspace/`, `chain.json`, and `private.json` into the scorer container, and the tests run there against the chain. The host checks the reply against `target.yaml`, and an LLM reads the transcript for `rubric.md`.

## Recipes

### Simple quiz

New quizzes use Harbor task folders under `tasks/`.
Read [the Harbor guide](harbor.md) for final-reply inputs and the free check.
New tasks use Harbor.

### Task with a fresh chain

New chain tasks use Harbor sidecars.
Read [the Harbor guide](harbor.md) for setup, context files, and Forge checks.

### Task on a fork

Declare the sidecar and its pinned block in the task's compose file.
List the required secret's variable name in `metadata.required_env` in `task.toml`.
Read [the Harbor guide](harbor.md) for the free check and the manual fork check.

## Check your task

Install the runner as the [README](../README.md#quickstart) says, then run:

```sh
uv run ethevals free-check --output results/author-task
```

`free-check` lints every Harbor task and runs two trials without a model:

- In the oracle run, every check must pass.
- In the nop run, at least one check must fail.

Each trial writes named checks and their reasons in `verifier/checks.json`.
The command needs Docker and skips criteria that need a paid judge.
See [Harbor tasks](harbor.md) for selectors and output paths.

## Open the pull request

Run the free checks that CI runs. They need Docker, Node.js 22, and pnpm 9.14.2:

```sh
rm -rf results/ci-checks
(cd site && pnpm install --frozen-lockfile)
env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_AUTH_TOKEN -u EXA_API_KEY \
	uv run python scripts/ci.py checks --output results/ci-checks
```

Git ignores folders named `lib`, `out`, and `cache`, so don't use those names in an eval.
After merge, CI runs the eval within the maintainers' budget and opens a pull request with the results.

## Runner details

The [runner README](../inspect-runner/README.md) covers the rest:

- [Captured files and build scoring](../inspect-runner/README.md#captured-files-and-build-scoring)
- [Limits and errors](../inspect-runner/README.md#limits-and-errors)
- [Compose and agents](../inspect-runner/README.md#compose-and-agents)
- [Setup and solution contract](../inspect-runner/README.md#setup-and-solution-contract)
- [Forks](../inspect-runner/README.md#forks)
- [CI and publication](../inspect-runner/README.md#ci-and-publication)
