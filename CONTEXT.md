# ETH Evals

ETH Evals measures how well AI agents do Ethereum work, and what bare models know about Ethereum. Teams add evals as folders, and the system runs, scores, and publishes them. This file is the shared vocabulary.

## Who we evaluate

**Agent**:
A harness paired with a model, such as Claude Code with Opus 5.5.
_Avoid_: model, when you mean the thing under test

**Harness**:
The program that drives a model, with its own tools, system prompt, and loop. Claude Code, Codex CLI, and OpenCode are harnesses.

**Model**:
The language model inside an agent, or on its own in the vanilla mode.

**Mode**:
What an agent or model can reach during an epoch. Each eval lists the modes it runs in.

**Vanilla**:
A mode where a bare model answers the prompt through a plain API call, with no harness, no tools, and no workspace.

**Internet**:
A mode where an agent works as it normally would, with the web, a shell, its workspace, the chain, and the eval's services. No Ethereum skills are installed.

**Skills**:
The internet mode with the repo's Ethereum skills pack installed.

## What an eval is made of

**Eval**:
One folder: `eval.yaml` plus up to four folders, `workspace/`, `setup/`, `scorer/`, and `solution/`, each with one job. The files present decide how the eval runs and how it is scored.
_Avoid_: test, task, sample

**Prompt**:
The message the agent or model receives, written the way a real user would send it.
_Avoid_: task, input, instruction

**Workspace**:
The files the agent starts with: the eval's `workspace/` folder as shipped, plus the chain file when the eval has a chain.
_Avoid_: starter, template, seed

**Service**:
A container an eval needs next to the agent's own, such as a chain.
_Avoid_: sidecar

**Chain**:
The Ethereum chain an eval declares with `chain` in `eval.yaml`, either a fresh local chain or a fork. The agent reaches it only through the filtered RPC, which refuses chain controls.
_Avoid_: node

**Fork**:
A chain that starts from a named network, `mainnet` or `base`, at a pinned block.

**Setup**:
The forge script in `setup/` that prepares the chain before the agent starts. It never reaches the agent.

**ChainSetup**:
The Solidity helper that a setup script inherits. It funds addresses and writes the chain file and the private file.

**Chain file**:
`chain.json`, which setup writes for the agent: the RPC URL, the chain ID, and the values setup records. The tests read the same file.

**Private file**:
`private.json`, which setup writes for the tests alone. The agent never sees it.

**Scorer**:
One way to decide checks: a target, tests, or a rubric. An eval's `scorer/` folder holds one or more, and never reaches the agent.
_Avoid_: verifier, grader kind

**Target**:
The expected final reply: one accepted answer, or a list where any one counts.
_Avoid_: answer key, flag

**Tests**:
Forge test files in `scorer/tests/` that check the agent's code, the chain, or both.

**Rubric**:
A list of yes-or-no questions a grader answers about the agent's work.
_Avoid_: criteria

**Grader**:
The model that answers a rubric.
_Avoid_: judge

**Reference solution**:
A working answer that ships with the eval in `solution/`. It proves every check can pass. A quiz's reference is its target.
_Avoid_: golden answer, oracle

**Motivation**:
One line on why the eval exists.
_Avoid_: notes, description

**Quiz**:
An eval that asks a question with a fixed answer and grades the reply with a target. The word describes an eval. It is not a field.

## Where an epoch runs

**Work network**:
The network the agent shares with the chain and the eval's services.

**Grading network**:
The network the scorer container shares with the chain. The agent can't reach the scorer.

## How evals are scored

**Epoch**:
One agent, or one bare model in the vanilla mode, on one eval in one mode at one effort, executed once. The epoch number counts repeats: epoch 2 is the same combination executed again. An epoch passes only if every check passes.
_Avoid_: run, trial

**Attempt**:
One execution of an epoch. The first is attempt 1. An error can lead to another, up to `max_attempts`.

**Time limit**:
The wall-clock time one epoch gets, the same for every eval. An epoch that reaches it is scored on what the agent left.

**Cost limit**:
The model spend one epoch can reach, the same for every eval.

**Check**:
One named pass-or-fail result about an epoch, with a one-line reason. A target check takes the target's name, a test check takes the test function's name, and a rubric check takes the question's heading.

**Compile**:
The check that the tests and the agent code they import compile. If it fails, every test fails with it.

**Score**:
The share of scored epochs that passed. Errors do not enter the denominator. The board shows counts, without error bars.
_Avoid_: partial score

**Eval hash**:
A fingerprint of captured file paths and bytes in an eval folder, excluding local artifacts. Evals that declare skills also include the skills pack. Results under an older hash do not describe the current eval.

**Results row**:
The latest record of one epoch: its eval, agent, mode, checks, and cost. It names the local log and links to published logs.

**Log**:
The full record of an epoch, including the transcript.
_Avoid_: trace

## How evals are checked

**Free check**:
The checks a pull request runs with no model: validation, a reference pass that must pass every check, and an untouched pass that must fail.

**Fork check**:
The reference and untouched passes for a fork eval. A maintainer starts it by hand on a pull request, because it needs the network's RPC secret.

## How evals are grouped

**Pillar**:
The area of Ethereum an eval covers: Concepts, Transactions, Building, or Security.
_Avoid_: category, stage, track

## What the system publishes

**Agent table**:
Scores for agents in the internet or skills mode.
Its current board tab label is "Agent board", a working label that can change.

**Knowledge table**:
Scores for bare models in the vanilla mode.
Its current board tab label is "Pre-training (Vanilla)", a working label that can change.

**Dataset**:
The vanilla evals graded by a target alone, published to Hugging Face as JSONL, one line per eval with its prompt and target.

## Retired words

Don't use these words for ETH Evals concepts.

| Word | Say instead |
| --- | --- |
| type, and quiz, build, act, or scenario as a type | what the folder holds: tests, a chain, a target. "Quiz" stays as a description |
| check script | tests |
| working limit, total limit | time limit |
| private network | work network |
