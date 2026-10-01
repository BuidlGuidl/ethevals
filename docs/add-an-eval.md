# Add an eval

An eval is a folder under `evals/<pillar>/<name>/`, where the pillar is `concepts`, `transactions`, `building`, or `security`.
The folder path is the eval ID.
You are done when `ethevals validate` passes, the reference pass of `ethevals check` passes every check, the untouched pass fails, and the PR's free checks pass.

## Prepare the checkout

Install Python 3.13, uv, Node.js 22 or later, and pnpm 9.14.2.
For any eval that runs in the internet or skills mode, start Docker with Compose support.
Give Docker at least 7 GiB for one epoch with a chain. Forks and extra services need more.
Run these commands from the repository root in one shell:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY
uv sync --frozen
```

## Lay out the folder

Copy the example below that is closest to your eval, and keep `eval_dir` set to the new path for the final checks:

```sh
cp -R evals/transactions/send-six-decimal-token evals/transactions/my-transfer
eval_dir=evals/transactions/my-transfer
```

Each path has one job. Only `scorer/` is required.
An eval with a `chain` needs `setup/setup.s.sol`, and `validate` rejects `setup/` without a `chain`.

| Path | Holds | The agent sees it |
| --- | --- | --- |
| `eval.yaml` | the prompt and the declaration | the prompt |
| `workspace/` | the agent's starting files: a README, a stub, a `foundry.toml`, source to read | yes, as shipped |
| `setup/` | `setup.s.sol` and the contracts only setup deploys | no |
| `scorer/` | `target.yaml`, `tests/*.t.sol`, and `rubric.md`, in any combination | no |
| `solution/` | the reference solution: files that replace workspace files at the same path, and an optional `solution.s.sol` | no |
| `compose.yaml` | extra services | it can call them |

The repository is public, so an agent with internet access can find scorer files. Don't rely on their secrecy.

`eval.yaml` takes these keys. Any other key fails validation.

| Key | Required | Holds |
| --- | --- | --- |
| `prompt` | yes | the message the agent gets |
| `motivation` | yes | one line on why the eval exists, shown on the board |
| `modes` | yes | any of `vanilla`, `internet`, and `skills` |
| `chain` | no | `anvil` for a fresh chain, or `{fork: mainnet, block: 23819000}` for a pinned fork. Omit it for no chain |
| `choices` | no | 2 to 26 answers for a multiple-choice quiz |

- `vanilla` sends the prompt to a bare model with no tools. Use it only when the eval has no `chain`, no `workspace/`, and no `scorer/tests/`, because a bare model has nowhere to put work.
- `internet` runs an agent with the web, a shell, the workspace, and the chain.
- `skills` is `internet` with the whole [skills pack](../skills/README.md). Evals don't ship skills. Send helpful notes to the pack upstream. Pack changes update the hash of every eval that declares `skills`.

### Pick the scorers

Use one or more scorers. An epoch passes when every check passes.

| File | Grades | Check names |
| --- | --- | --- |
| `scorer/target.yaml` | the final reply, with Inspect's `match`, `pattern`, or `choice` | the file's `name`, default `answer` |
| `scorer/tests/*.t.sol` | the agent's code, the chain, or both, with Forge | each test function's name, plus `compile` |
| `scorer/rubric.md` | the transcript, with the agent's compiled source in front when it compiled | each `##` heading |

The scorer picks the test tool from the file names in `scorer/tests/`. Forge is the one test tool, and it claims `*.t.sol` files.
A file that no test tool claims is a helper that tests can import.
`compile` is one check per eval, shared by every test tool.

Check names must be unique across the eval, and `compile` is reserved.
Name targets and rubric questions with `[a-z][a-z0-9_]*`.

### Write a prompt a real person would send

The agent must not know it is being tested.
Write the prompt the way a user would, and give the agent only what that user would give.
`ethevals validate` rejects these words in the prompt and in `workspace/` files, as whole words in any case: epoch, grader, rubric, score, benchmark, eval, and "being tested".
`ethevals check` applies the same rule to `chain.json` after setup runs.
Reviewers ask one question: would a real person send this?

The agent sees only these things:

- the prompt, with the choices under it for a multiple-choice quiz;
- `workspace/` as shipped, at `/workspace`;
- `/workspace/chain.json` and the chain at `http://chain:8545`, when the eval has a chain;
- the services in `compose.yaml`;
- the skills pack, in the skills mode.

The runner adds no notes, no `foundry.toml`, and no Solidity libraries. The agent picks its own tools and libraries.

## Write a quiz

[agent-registries](../evals/concepts/agent-registries) has only `eval.yaml` and `scorer/target.yaml`. A quiz has no `workspace/`. Its one check is `erc_number`.

```yaml
# eval.yaml
motivation: Check whether a model knows the ERC for agent discovery and trust.
prompt: which ERC defines onchain identity, reputation and validation registries for AI agents? just the number please
modes: [vanilla, internet, skills]

# scorer/target.yaml
name: erc_number
method: match
target: '8004'
location: end
```

- Quote numeric targets and addresses so YAML keeps them as strings.
- `target` is one answer or a list where any one counts. A vanilla quiz takes one target, or a one-item list.
- `match` is exact and ignores case by default. `location`, `ignore_case`, and `numeric` pass through to Inspect's `match()`. `location` takes `exact`, `begin`, `end`, or `any`.
- For a regex, set `method: pattern`, put the regex in `pattern`, and put a complete matching reply in `reference`.
- For multiple choice, list the `choices` in `eval.yaml` and set `target` to the right uppercase letter. See the [wei-per-ether fixture](../inspect-runner/tests/fixtures/concepts/wei-per-ether).
- CI publishes every eval that declares `vanilla` and is graded by a target alone to Hugging Face, targets included. Agents in the internet mode can look those targets up.

## Write a chain eval

[send-six-decimal-token](../evals/transactions/send-six-decimal-token) uses all four folders.
Next to `eval.yaml`, it has `workspace/README.md`, `setup/setup.s.sol` with the `setup/Token.sol` it deploys, `scorer/tests/Transfer.t.sol`, `scorer/rubric.md`, and `solution/solution.s.sol`.

```yaml
chain: anvil
motivation: Test whether an agent reads token decimals before signing an exact transfer.
modes: [internet, skills]
prompt: |
  can you send 12.5 tokens to the recipient in chain.json? the file has the rpc url,
  the token address, the recipient and the private key of my funded account.
```

The token has 6 decimals, and the prompt doesn't say so.
Checks: `compile`, `test_recipient_balance`, and the rubric's `verified_transfer`.

### Prepare the chain with setup

Before the agent starts, the runner runs `forge script setup/setup.s.sol --broadcast --slow --rpc-url http://127.0.0.1:8546` in the chain container, on the unfiltered RPC:

```solidity
import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";
import {Token} from "./Token.sol";

contract Setup is ChainSetup {
    function run() external {
        Vm.Wallet memory me = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        Vm.Wallet memory deployer = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        address recipient = vm.randomAddress();
        fund(me.addr, 10 ether);
        fund(deployer.addr, 1 ether);

        vm.startBroadcast(deployer.privateKey);
        Token token = new Token(me.addr);
        vm.stopBroadcast();

        chainRecord("privateKey", bytes32(me.privateKey));
        chainRecord("recipient", recipient);
        chainRecord("token", address(token));
    }
}
```

`ChainSetup` adds three functions to a plain forge script:

| Function | What it does |
| --- | --- |
| `fund(addr, amount)` | sets the address's ETH balance on the chain with `anvil_setBalance` |
| `chainRecord(name, value)` | adds a field to `chain.json`, which the agent and the tests read |
| `privateRecord(name, value)` | adds a field to `private.json`, which only the tests read |

The record functions take an address, a `uint256`, a `bytes32`, or a string.
`chain.json` always has `rpcUrl` and `chainId`, so this setup gives the agent `rpcUrl`, `chainId`, `privateKey`, `recipient`, and `token`.

- Make keys with `vm.randomUint`, never from a label. The repository is public, so anyone can derive a key made from a label.
- Use `fund`, not `vm.deal`. A forge script runs in Forge's simulation first and then sends only the broadcast transactions, so `vm.deal` changes only the simulation.
- The chain image ships only forge-std and `ChainSetup`. Write setup contracts that import nothing else, or vendor what they need inside `setup/`.
- To deploy a contract the agent should read, keep its one copy in `workspace/` and import it from setup. That contract imports only files the workspace ships.
- Don't ship `workspace/chain.json` or `workspace/private.json`. Setup writes those files, and `validate` rejects them.
- Setup has 120 seconds. A setup failure is an error, not a failed check.

### Check the chain with a Forge test

[Transfer.t.sol](../evals/transactions/send-six-decimal-token/scorer/tests/Transfer.t.sol) imports only forge-std. Its two functions:

```solidity
function setUp() public {
    string memory chain = vm.readFile("chain.json");
    recipient = chain.readAddress(".recipient");
    token = IERC20(chain.readAddress(".token"));
    vm.createSelectFork("chain");
}

function test_recipient_balance() public view {
    assertEq(token.balanceOf(recipient), 12_500_000, "recipient holds 12.5 tokens in base units");
}
```

- Read `chain.json` and `private.json` with `vm.readFile`. They sit in the test's working directory.
- Fork the finished chain with `vm.createSelectFork("chain")`. Changes a test makes stay in Forge's fork.
- Before tests run, the runner stops the agent's processes and mines one block, so every transaction the agent sent is in a block.
- Check only what the prompt asks. A check on the sender's transaction count would grade something the user never said.
- A test that imports nothing from the workspace, like this one, fails `compile` only on an author error.

### Write the reference solution

[solution/solution.s.sol](../evals/transactions/send-six-decimal-token/solution/solution.s.sol) plays the agent.
It reads `chain.json`, computes `125 * 10 ** token.decimals() / 10`, and broadcasts the transfer from `privateKey`.
The runner runs it in the scorer container with `forge script --broadcast` against `http://chain:8545`, the filtered RPC the agent uses.
Use only what the agent gets: the prompt, the workspace, and `chain.json`. Don't read `private.json`.

## Write a build eval

[erc20-points-token](../evals/building/erc20-points-token) asks the agent to write a contract:

```yaml
motivation: Check whether an agent can build a capped community token on a well-known library.
modes: [internet, skills]
prompt: |
  can you help me build a token for our community? I created an empty file at src/BuilderPoints.sol.
  call it Builder Points (BPT), with the same decimals as USDC. mint 100,000 to whoever deploys it.
  the deployer should be able to mint more later, but the total supply must never go over 1,000,000.
  it's a Foundry project on solidity 0.8.30.
```

Ship this `workspace/foundry.toml` in a Foundry eval. The agent can change it, and grading never uses it.

```toml
[profile.default]
src = "src"
test = "test"
libs = ["lib"]
solc = "0.8.30"
```

The stub `workspace/src/BuilderPoints.sol` fixes the contract name, a no-argument constructor, and the `mint` signature.
The test relies on those and on standard ERC-20, nothing else.
[BuilderPoints.t.sol](../evals/building/erc20-points-token/scorer/tests/BuilderPoints.t.sol) has ten test functions. Its imports, `setUp`, and the first test:

```solidity
import {Test} from "forge-std/Test.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";
import {BuilderPoints} from "workspace/src/BuilderPoints.sol";

function setUp() public {
    points = new BuilderPoints();
    token = IERC20(address(points));
}

function test_decimals_match_usdc() public view {
    assertEq(token.decimals(), 6, "decimals");
}
```

`scorer/rubric.md` asks one question, `uses_standard_library`: did the agent build the ERC-20 on a well-known library such as OpenZeppelin or Solady?
`solution/src/BuilderPoints.sol` overlays the stub with OpenZeppelin `ERC20Capped` and `Ownable`.
A file in `solution/` replaces the workspace file at the same path. So the solution lives at `solution/src/BuilderPoints.sol`, matching the stub at `workspace/src/BuilderPoints.sol` that the test imports. Keep the workspace a normal Foundry project, with contracts under `src/`.

Git ignores `lib/` at any depth, so a solution that uses a library ships as one flattened file.
Write it in a scratch Foundry project with the library installed through `forge install`.
Then run `forge flatten src/X.sol` there and save the output as `solution/src/X.sol` in the eval.
Check that the file has one SPDX line and one pragma, and that the pragma matches the version in the prompt.

Checks: `compile`, the ten test functions, and `uses_standard_library`.

### Import the agent's code

Import the agent's file by its workspace path with a `workspace/` prefix, as `BuilderPoints.t.sol` does.
A Scaffold-ETH 2 contract, for example, is `workspace/packages/hardhat/contracts/YourContract.sol`.

- Name the file in the prompt or with a stub, the way a real user would.
- The runner copies the agent's final workspace into the scorer under `workspace/`, without `.git`, `out`, or `cache`, and keeps only `.sol` files from `node_modules`. The copy holds at most 50 MiB and 20,000 files.
- Forge compiles your tests and what they import, and nothing else. A broken file elsewhere in the workspace doesn't matter.
- A missing file fails `compile` with Forge's reason, such as `Source "workspace/src/Vault.sol" not found`. One missing import fails every test, so `compile` is all or nothing.
- Apart from the agent's files, import only forge-std in tests. Reach the agent's contract through forge-std's interfaces, such as `forge-std/interfaces/IERC20.sol`, and `address` casts.
- The agent's code compiles against the libraries the agent installed with `forge install` or npm. The runner maps each agent project's libraries only for files in that project.
- No image ships a Solidity compiler. Forge installs the version each file's pragma asks for, in the agent's container and in the scorer, so any released 0.8.x works. If the task depends on a version, name it in the prompt and in `foundry.toml`.
- A pragma that no released compiler satisfies fails `compile`. A failed compiler download is an error, not a failed check, so the epoch can get another attempt.
- Tests can read only `chain.json` and `private.json`. FFI is off.

Forge test results become checks:

- The check name is the test function's name, without the suite path or `()`.
- The reason is the assertion message. `assertEq(a, b, "recipient balance")` fails as `recipient balance: 12500000 != 13000000`, so write the message you want on the board.
- `validate` rejects `testFail*` names, because a failing one hides every other test in its suite. Use `vm.expectRevert`.
- A reverting `setUp()` or constructor turns its suite into one failed check named `<Contract>.setUp` or `<Contract>.constructor`.

The agent's contract runs inside Forge's test environment, so it can call the cheatcode address and fake what a test reads with `vm.mockCall` or `vm.store`.
This is allowed for now and watched in transcripts.

## Add a rubric

Add `scorer/rubric.md` with one yes-or-no question per `## name` heading:

```markdown
## verified_transfer

Before reporting success, did the agent confirm on-chain that the transfer landed, for example by reading the transaction receipt or the recipient's token balance?
```

- A rubric works on any eval, alone or with a target or tests.
- The grader reads the whole transcript: tool calls with their inputs and outputs, and the final reply. When the tests compiled the agent's code, that source comes first.
- Evidence has no size cap. The runner trims it only when it would exceed the grader model's context window.
- `check` skips rubrics, so the reviewer reads `rubric.md` in the PR. A rubric-only eval has no reference pass or untouched pass.

## Use a fork

To start from real mainnet or Base state, declare a fork and pin its block:

```yaml
chain: {fork: mainnet, block: 23819000}
```

- The block is required, so every epoch starts from the same state. The runner knows `mainnet` and `base`.
- The runner reads the network's RPC URL from a repository secret and passes it only to anvil in the chain container. The agent never sees it, and the runner replaces it with `<fork rpc>` in RPC replies and command output. Anvil runs with the network's chain ID and no prefunded accounts.
- The runner runs `forge test --no-storage-caching` on forks, so a cached read from an earlier epoch can't pass a wrong answer.
- On a fork, the chain container gets 1 GiB, and setup and `forge test` each get 600 seconds.
- To check a fork eval locally, set `MAINNET_RPC_URL` or `BASE_RPC_URL` to an archive RPC URL.

[vesting-claim](../evals/transactions/vesting-claim) is the example.
A vesting contract holds 50,000 USDC, and its beneficiary says the funds are stuck. The owner asks the agent to get the USDC to the beneficiary.
Setup deploys `workspace/src/Vesting.sol` from the agent's account, with a schedule that ended a year before the fork block.
Three `vm.rpc` calls move the USDC from a holder that has enough at the pinned block:

```solidity
vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(HOLDER), '"]'));
// ERC-20 balances can be funded at the future CREATE address before deployment.
vm.rpc("eth_sendTransaction", string.concat('[{"from":"', vm.toString(HOLDER), '","to":"', vm.toString(USDC),
    '","data":"', vm.toString(abi.encodeCall(IERC20.transfer, (address(vesting), 50_000e6))), '"}]'));
vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(HOLDER), '"]'));
```

- A `vm.rpc` call runs on the chain at once, during Forge's simulation. The USDC lands at the contract's address before the broadcast deploys the contract.
- Send from the holder with `vm.rpc`, not a broadcast. A broadcast needs the sender's key, and setup has none for the holder.
- Stop impersonating before `run()` returns.

Checks: `compile`, `test_beneficiary_holds_the_usdc`, `test_vesting_contract_is_empty`, and the rubric's `explained_the_release`.
The reference solution calls the contract's own `release(usdc)` from the agent's key.

The free check on a PR has no secrets, so for a fork eval it validates the folder and skips both passes.
A maintainer reads the PR, then dispatches the `fork-check.yml` workflow with the PR number and the full SHA of the commit they read.
If the PR head is no longer that commit, the workflow fails.
Otherwise it runs both passes with the `MAINNET_RPC_URL` and `BASE_RPC_URL` secrets and no model, and posts a `fork check` status on that commit.
The eval merges only after that status passes.

## Add an extra service

To give the agent another service, create `compose.yaml` in the eval folder with only the extra services and named volumes:

```yaml
services:
  catalog:
    image: python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f
    command: [python, -m, http.server, "8080"]
    mem_limit: 64m
    networks: [work]
```

- Pin each image by digest, and set a positive `mem_limit`. Give Docker enough memory for the sum plus the stock services.
- Join only `work`, the default when `networks` is absent. The agent and the chain share `work`. The scorer can't reach the service.
- Don't redeclare `default`, `scorer`, `chain`, or the networks, which the runner owns. Don't copy stock image tags.
- Don't use host mounts, published ports, privileged containers, custom builds, or inherited host environment values. For persistent data, use a named volume. See the [Compose rules](../inspect-runner/README.md#compose-and-agents).

## Check your eval

With `eval_dir` set by your copy step, run:

```sh
uv run ethevals validate --evals "$eval_dir"
rm -rf results/author-eval
uv run ethevals check --evals "$eval_dir" --output results/author-eval
```

`validate` needs no Docker and no model. It checks the keys, the folders, the vanilla rule, the check names, and the prompt rule, then prints the eval ID and hash.

`check` makes no model calls and skips rubrics. Every eval with tests or a chain needs a reference solution. `check` runs `epochs` from `config.yaml` twice:

- The reference pass applies every reference the eval has: the target's reference reply, the `solution/` overlay, and `solution/solution.s.sol`. Every check must pass.
- The untouched pass sends an empty reply and leaves the workspace and the chain as setup left them. At least one check must fail.

Expected final lines, where `<epochs>` is the configured count:

```text
<epochs> results rows: results/author-eval/reference/rows.jsonl
<epochs> results rows: results/author-eval/empty/rows.jsonl
```

Read both row files. Every reference row needs `status: passed`, and every untouched row needs `status: failed`.
If the command fails, use these steps:

- For a declaration error, fix the named key or file, then rerun `validate`.
- For `status: error`, read `error_reason` and the log at `log_file`, relative to that pass's output folder. Fix setup failures before you submit.
- For a failed reference, read each failed check's `reason`: Forge's compiler error, your assertion message, or a `<Contract>.setUp` or `<Contract>.constructor` failure.
- If the untouched pass passes, strengthen the tests so they reject unfinished work.
- For a Docker capacity error, increase Docker memory or reduce concurrency in the runner configuration.

For a chain eval, prove the test catches a wrong answer. Change `solution.s.sol` to send the wrong amount and rerun `check`.
The reference pass must fail with your assertion message, not an error. Then restore `solution.s.sol`.

## Prepare the pull request

- Use regular files. The loader rejects symlinks and hard links.
- Git ignores `lib`, `out`, and `cache` at any depth. Don't use those names for other authored files.
- Remove stray files before the final check. Eval hashes include uncommitted files.
- Keep generated logs and rows out of the PR, including `results/rows.jsonl`.

To reproduce the PR's `Free checks` job, run:

```sh
(cd site && pnpm install --frozen-lockfile)
rm -rf results/ci
uv run python scripts/ci.py checks --output results/ci
git diff --check
```

This needs Docker and takes several minutes. It makes no paid calls.
A reviewer checks the prompt's facts and any rubric.

Paid runs start after merge, once a maintainer sets `ETHEVALS_BUDGET_USD` above its default of zero.
CI runs each missing epoch as its own job, with a 2-hour time limit and a $20 cost limit. An epoch that reaches the time limit is scored on what the agent left.
CI opens a results PR, and merging it puts the results on the board. Changing an eval file changes its hash and makes earlier results stale.
See [CI and publication](../inspect-runner/README.md#ci-and-publication) for operator steps.
