# ETH Evals

ETH Evals measures how well AI agents do Ethereum work, and what bare models know about Ethereum. Teams add tasks as Harbor task folders, and the system runs, verifies, and publishes them. This file is the shared vocabulary. It follows Harbor's words, and keeps our own only where Harbor has none.

## Who we evaluate

**Agent**:
The program that drives a model, with its own tools, system prompt, and loop. Claude Code, Codex CLI, and OpenCode are agents. The board names an agent on a model, such as Claude Code on Opus 5.5.
_Avoid_: harness

**Model**:
The language model an agent drives, or a bare model on its own in the vanilla mode.

**Mode**:
What an agent or model can reach during a trial. Each task lists the modes it runs in.

**Vanilla**:
A mode where a bare model answers the instruction through one plain API call, with no agent, no tools, and no environment.

**Internet**:
A mode where an agent works as it normally would, with the web, a shell, its environment, and the task's sidecars. No Ethereum skills are installed.

**Skills**:
The internet mode with the repo's Ethereum skills pack installed.

**Plan**:
A Claude or ChatGPT subscription that pays for an agent's model calls in place of an API key.
_Avoid_: sub, subscription login

## What a task is made of

**Task**:
One Harbor task folder: its settings, an instruction, an environment, tests, and a solution. "Eval" survives only in the product name.
_Avoid_: eval, test, sample

**Instruction**:
The message the agent or model receives, written the way a real user would send it.
_Avoid_: prompt, task

**Environment**:
The container the agent works in, with the files it starts with.
_Avoid_: workspace, sandbox, starter

**Sidecar**:
A container a task runs next to the agent's own, such as a chain.
_Avoid_: service

**Chain**:
An Ethereum chain a task runs as a sidecar, either fresh or a fork. The agent reaches it only through the filtered RPC, which refuses chain controls.
_Avoid_: node

**Fork**:
A chain that starts from a named network at a pinned block.

**Setup**:
The forge script that prepares the chain before the agent starts. It never reaches the agent.

**ChainSetup**:
The Solidity helper that a setup script inherits. It funds addresses and writes the chain context and the private chain context.

**Chain context**:
`chain_context.json`, which setup writes for the agent: the RPC URL, the chain ID, and the values setup records. The tests read the same file.

**Private chain context**:
`private_chain_context.json`, which setup writes for the tests alone. The agent never sees it.

**Verifier**:
What decides a trial's checks once the agent stops. A task's tests and criteria never reach the agent while it works.
_Avoid_: scorer, grader

**Target**:
The expected final reply to a quiz: one accepted answer, or a list where any one counts.
_Avoid_: answer key, flag

**Criteria**:
Yes-or-no questions a judge answers about the agent's work, kept in a RewardKit judge file in the task's tests. Each question is one check.
_Avoid_: rubric

**Judge**:
The model that answers criteria. It runs in the verifier.
_Avoid_: grader

**Solution**:
A working answer that ships with the task. It proves every check can pass.
_Avoid_: reference solution, golden answer, oracle

**Description**:
One line on why the task exists, kept in the `[task]` table.
_Avoid_: motivation, notes

**README**:
The task's `README.md`, written for people. It quotes the instruction, names the areas the task touches and the gotchas the instruction leaves out, says what each check proves, and says why it matters beyond the task. The agent never sees it.
_Avoid_: motivation, notes

**Quiz**:
A task that asks a question with a fixed answer and checks the reply against a target. The word describes a task. It is not a field.

## How tasks are run and checked

**Trial**:
One agent on a model, or one bare model in the vanilla mode, on one task in one mode at one effort, executed once. The trial number counts repeats. A trial passes when its reward is 1.
_Avoid_: epoch, run

**Job**:
A batch of trials run together. Its `n_attempts` is how many scored trials it runs for each task, agent, and mode.

**Retry**:
Running a trial again after an error, up to the job's retry limit. A retry adds no scored trial. Harbor's exclusion list decides which errors get one.
_Avoid_: attempt

**Time limit**:
The wall-clock time an agent or verifier gets. Harbor's default applies unless a task sets its own, and a task sets one only when it needs it. A trial that reaches it is checked on what the agent left.

**Check**:
One named pass-or-fail result about a trial, with a one-line reason. A test check takes its test function's name, and a criteria check takes its criterion's name.

**Reward**:
Harbor's result for a trial, written by RewardKit. `reward` is 1 only when every check passes. A task can add other reward keys.

**Compile**:
The check that the tests, and the agent code they import, compile. A task has one, shared by every test tool. If it fails, every test fails with it.

**Score**:
How many of an agent's scored trials passed, shown as a count such as 3 of 5. Errors don't count.
_Avoid_: partial score

**Cost**:
The API price of a trial's model calls, recorded the same way whether a plan or an API key paid.

**Task hash**:
Harbor's package digest of a task's files, saved in each trial's lock. Changing a task's files reruns every mode for that task.

**Skills hash**:
A fingerprint of the skills pack's files. Only skills-mode trials include it in their identity, so a skills change reruns only skills-mode trials.

**Results row**:
The latest record of one trial: its task, agent, model, mode, checks, cost, judge, and whether a plan or a key paid. It links the trajectory.

**Trajectory**:
The full record of what the agent did in a trial.
_Avoid_: log, transcript, trace

## How tasks are checked on pull requests

**Free check**:
The checks a pull request runs with no model: lint, an oracle run that must pass every check, and a nop run that must fail.

**Oracle run**:
A trial where the solution is applied in place of an agent's work.

**Nop run**:
A trial where nothing is done, which proves the checks don't pass on untouched work.

**Fork check**:
The oracle and nop runs for a fork task. A maintainer starts it by hand on a pull request, because it needs the network's RPC secret.

## How tasks are grouped

**Pillar**:
The area of Ethereum a task covers: Concepts, Transactions, Building, or Security.
_Avoid_: category, stage, track

## What the system publishes

**Agent table**:
Scores for agents in the internet or skills mode.
Its board mode labels are "Internet" and "Internet + Skills".

**Knowledge table**:
Scores for bare models in the vanilla mode.
Its board mode label is "Model only".

**Dataset**:
Every task, published to Hugging Face as Harbor task folders.
