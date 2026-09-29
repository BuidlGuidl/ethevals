# Add an eval

Add a folder under `evals/<pillar>/<name>/`.
Use `concepts`, `transactions`, `building`, or `security` for the pillar.
The folder path supplies the eval ID.
`check` runs your reference and an untouched case: an empty reply for quizzes, and the starting workspace for builds and acts.
Rows go under `reference/` and `empty/`.
Finish when the reference passes, the untouched case fails, and the PR's free checks pass.

## Prepare the checkout

Install Python 3.13, uv, Node.js 22 or later, and pnpm 9.14.2.
For builds and acts, start Docker with Compose support.
Give Docker at least 7 GiB for one stock act epoch, including 1 GiB for the host.
Extra services need more memory. The default concurrency is one.
Vanilla quiz checks need no Docker.

Run these commands from the repository root in one shell:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY
uv sync --frozen
```

Check an unchanged quiz before you create your copy:

```sh
rm -rf results/author-guide/agent-registries
uv run ethevals check --evals evals/concepts/agent-registries --output results/author-guide/agent-registries
```

Expected final lines for this example:

```text
3 results rows: results/author-guide/agent-registries/reference/rows.jsonl
3 results rows: results/author-guide/agent-registries/empty/rows.jsonl
```

`check` uses scripted answers, makes no model calls, and skips rubrics.
For paid plans, `--models opus-5.5 --modes vanilla` selects a model; `--agents claude-code-opus-5.5 --modes internet` selects an agent.

## Choose an example to copy

Use one of the sections below.
Run its copy command only when the destination does not exist.
Replace the destination with your eval's name, and keep `eval_dir` set to that path for the final checks.

Edit `eval.yaml` with your prompt, one-line `motivation`, `type`, and `modes`.
Put the agent's starting files under `workspace/`.
Keep targets, tests, rubrics, and reference solutions under `scorer/`.
The scorer files select how the runner grades the eval.
The runner does not copy them into the agent's workspace, but the repository publishes them.
Do not rely on their secrecy from an agent with internet access.

Use `[vanilla]` for a bare-model quiz, or `[vanilla, internet]` to include agents.
Hugging Face publication includes targets, so internet-mode agents can look them up.
Use `[internet]` for builds and acts.
The `scenario` type is not supported yet.

Add `skills` to `modes` to run agents with the whole [skills pack](../skills/README.md).
Skills mode uses the internet mode's tools and limits, with an index in each harness's instruction file.
Pack changes update the hashes of every eval that declares `skills`.

### Write a free-text quiz

Copy [agent-registries](../evals/concepts/agent-registries):

```sh
cp -R evals/concepts/agent-registries evals/concepts/my-agent-registry
eval_dir=evals/concepts/my-agent-registry
```

Replace the prompt in `eval.yaml` and the answer in `scorer/target.yaml` together.
The example asks for an ERC number. Its complete target file is:

```yaml
name: erc_number
method: match
target: '8004'
```

Quote numeric targets and addresses so YAML keeps them as strings.
Use stable check names matching `[a-z][a-z0-9_]*`. The default name is `answer`.
The default match is exact and case-insensitive.
For pattern matching, supply `method: pattern`, a regex in `pattern`, and a matching complete reply in `reference`.
`location` (`exact`, `begin`, `end`, or `any`), `ignore_case`, and `numeric` pass through to Inspect's `match()`.
Vanilla quizzes accept one target, including a single-item list.
Keep `workspace/.gitkeep` so Git preserves the required empty directory.

### Write a multiple-choice quiz

Copy [wei-per-ether](../evals/concepts/wei-per-ether):

```sh
cp -R evals/concepts/wei-per-ether evals/concepts/my-unit-conversion
eval_dir=evals/concepts/my-unit-conversion
```

Set the prompt and 2 to 26 nonblank `choices` in `eval.yaml`.
The example's choices are `10^6`, `10^9`, `10^18`, and `10^24`.
Its complete `scorer/target.yaml` is:

```yaml
name: wei_conversion
target: C
```

Set `target` to the correct uppercase letter in the listed order.
The presence of `choices` selects multiple-choice scoring.
The runner preserves the order and supplies `ANSWER: C` for this reference.

### Write a build eval

Copy [erc20-points-token](../evals/building/erc20-points-token):

```sh
cp -R evals/building/erc20-points-token evals/building/my-points-token
eval_dir=evals/building/my-points-token
```

1. Define the contract interface and required behavior in `eval.yaml`.
2. Put the starting contract in `workspace/src/BuilderPoints.sol`.
3. Put a working answer in `scorer/solution/src/BuilderPoints.sol`.
4. Write behavior tests in `scorer/tests/BuilderPoints.t.sol`.

The reference files overlay the declared workspace at matching paths.
An optional `scorer/solution/run.sh` then runs with Bash in `/workspace`, with a 120-second limit.

Write Forge tests with `.t.sol` filenames under `scorer/tests/`.
The runner places them under `test/`, so the example imports `../src/BuilderPoints.sol`.
Its seven test functions cover the token's metadata, supply, owner, and transfers. The runner adds `forge:compile`.

Use Solidity 0.8.30 with the installed OpenZeppelin 5.4.0 and forge-std 1.9.7 libraries.
Use the `@openzeppelin/contracts/` and `forge-std/` remappings.
For another dependency, ship Solidity files under `workspace/src/` and use relative imports.
Do not add `workspace/foundry.toml`. The runner owns grading settings and ignores submitted replacements for its libraries.
Grading uses captured Solidity files under `src/` and `lib/`, plus your tests.
The scorer has internet access, but FFI and filesystem cheatcode permissions are disabled.
The compiler must already exist in the image.

If the prompt needs model grading, keep `scorer/rubric.md` with one yes-or-no question per `## name` heading.
For example, `uses_openzeppelin` asks whether the contract uses OpenZeppelin v5's ERC20 implementation.
If tests cover the whole prompt, remove the rubric file.
Rubrics require tests for source evidence.
See [build scoring](../inspect-runner/README.md#captured-files-and-build-scoring) for the evidence contract.

### Write an act eval

Copy [send-six-decimal-token](../evals/transactions/send-six-decimal-token):

```sh
cp -R evals/transactions/send-six-decimal-token evals/transactions/my-token-transfer
eval_dir=evals/transactions/my-token-transfer
```

The example asks for one signed transfer of 12.5 tokens after reading the token's decimals.
Keep `type: act` and `modes: [internet]`.

1. Prepare the chain in [scorer/setup.sh](../evals/transactions/send-six-decimal-token/scorer/setup.sh).
   Generate fresh keys and fund the agent's key.
   Keep expected state in a private file under `/eval`, as the example does with `private.json`.
2. Print one JSON object with a `files` mapping from relative workspace paths to text.
   The example returns `chain.json` with the public RPC URL, funded private key, sender, recipient, and token.
   Setup files reach both the agent and scorer workspaces. They cannot escape the workspace or replace declared files.
3. Adapt [scorer/solution/run.sh](../evals/transactions/send-six-decimal-token/scorer/solution/run.sh) to solve the prompt using only the agent's public information.
   Sign locally and submit through the supplied public RPC URL.
4. Adapt [scorer/check.py](../evals/transactions/send-six-decimal-token/scorer/check.py) to read the final chain state without changing it.
   Return a verdict for unwanted states, including no transfer, multiple transfers, and a wrong amount.

Prefer Bash with `cast` or `forge` for new act scripts. Use Python when it makes the script clearer.
Supply exactly one `scorer/check` or `scorer/check.<ext>` file.
Setup is optional and uses `scorer/setup` or `scorer/setup.<ext>`.
Give each script a shebang for its interpreter. The runner makes it executable and runs it directly.

Setup and check run in the chain container from `/eval`, where your scorer files sit under `scorer/`.
They receive `RPC_URL` for private Anvil controls, `PUBLIC_RPC_URL` for filtered RPC, and `SOLC` for the installed compiler.
The reference `run.sh` runs in the agent's container.
Both containers have `cast`, `forge`, `jq`, and internet access.
Forge runs offline, so pass `--use "$SOLC"`.
Setup and checks each have 120 seconds. Keep their output concise.

Keep setup output and service responses free of reference solutions and private expected state.
Keep chain controls out of services the agent can reach.
The public RPC accepts reads and signed raw transactions. It rejects unlocked sends and chain controls.
The check reads the chain after the runner stops the agent and mines one empty block.
Do not infer success from a file the agent can edit.

Print only the checks JSON to standard output. Send diagnostic text to standard error.
Use stable names matching `[a-z][a-z0-9_]*`.
Each value must contain exactly a boolean `passed` and a nonblank string `reason`.
Return every check on every execution. The runner prefixes names with `script:`.
The example checks the recipient's balance and the sender's transaction count.
Crashes, nonzero exits, and malformed JSON are errors, so they cannot satisfy the required untouched failure.

## Add an extra service if needed

The four examples use stock services and need no `compose.yaml`.
To add a service, create `compose.yaml` in your eval folder with only extra services and named volumes.
For example, this file adds an HTTP service at `http://catalog:8080`:

```yaml
services:
  catalog:
    image: python:3.13-alpine@sha256:79e7a9b9ff1cbceff819f856fb374477792a5967759d94df266de7b7b4120e6f
    command: [python, -m, http.server, "8080"]
    mem_limit: 64m
    networks: [private]
```

Pin each image by digest.
Set a positive `mem_limit` for each service, and budget Docker memory for their sum plus the stock services.
Join only `private`, which is also the default when `networks` is absent.
The runner owns `default`, `scorer`, `chain`, and network definitions.
Do not redeclare them or copy stock image tags into your file.
Do not use host mounts, published ports, privileged containers, custom builds, or inherited host environment values.
For persistent service data, declare a named volume and use a long-form `type: volume` mount.
See the [Compose rules](../inspect-runner/README.md#compose-and-agents) for allowed fields.

## Check your eval

With `eval_dir` set by your chosen copy step, run:

```sh
uv run ethevals validate --evals "$eval_dir"
rm -rf results/author-eval
uv run ethevals check --evals "$eval_dir" --output results/author-eval
```

`validate` prints the eval ID and hash after it checks the declaration and files.
`check` runs three reference epochs and three untouched epochs by default.
It selects vanilla for quizzes and internet for builds and acts.
Each invocation runs fresh epochs, even if the output directory exists.

Expected final lines for one eval:

```text
3 results rows: results/author-eval/reference/rows.jsonl
3 results rows: results/author-eval/empty/rows.jsonl
```

Read both row files.
Require `status: passed` for every reference and `status: failed` for every untouched epoch.
An untouched epoch needs at least one failed check. For example, the starting build compiles but fails behavior tests.
Each entry in `checks` has its own `passed` and `reason`.

If the command fails, use these steps:

- For a declaration error, fix the named field or missing file, then rerun `validate`.
- For `status: error`, read `error_reason` and the log at `log_file`, relative to that case's output folder.
  Fix script crashes, invalid JSON, or setup failures before submitting.
- For a failed reference, read each failed check's `reason`.
  Check compiler versions and imports for builds. Check setup values and token units for acts.
- If the untouched case passes, strengthen the checks so they reject unfinished work.
- If fewer rows appear, read the terminal error.
- For a Docker capacity error, increase Docker memory or reduce concurrency in the runner configuration.

For acts, temporarily change `run.sh` to send the wrong amount, then to send twice.
Rerun `check` each time.
The reference must fail with your script's reason, not an error.
Restore `run.sh`.

## Prepare the pull request

Use regular files. The loader rejects symlinks and hard links.
Avoid `lib`, `out`, and `cache` for authored files because Git ignores those names at any depth.
Remove stray files before the final check. Eval hashes include uncommitted files.
Keep generated logs and mock rows out of the PR, including `results/rows.jsonl`.

To reproduce the PR's `Free checks` job, run:

```sh
(cd site && pnpm install --frozen-lockfile)
rm -rf results/ci
uv run python scripts/ci.py checks --output results/ci
git diff --check
```

This needs Docker and takes several minutes.
It runs validation, free reference checks, Python tests, Docker proofs, dataset export, and site tests, typecheck, lint, and build.
It makes no paid calls. A reviewer checks the prompt's facts and any rubric.

A paid run starts only when CI runs after merge and a maintainer has set a budget.
`ETHEVALS_BUDGET_USD` defaults to zero, which blocks missing paid work.
CI opens a separate results PR. Merging that PR puts the results on the board.
Changing an included eval file changes its hash and makes earlier results stale.
Hugging Face publication is a separate manual workflow for vanilla quizzes.
See [CI and publication](../inspect-runner/README.md#ci-and-publication) for operator steps.
