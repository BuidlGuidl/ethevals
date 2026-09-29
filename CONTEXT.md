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
A mode where a bare model answers a quiz through a plain API call, with no harness and no tools.

**Internet**:
A mode where an agent works as it normally would, with the web, a shell, its workspace, and the eval's services. No Ethereum skills are installed.

**Skills**:
The internet mode with Ethereum skills installed. Not supported yet.

## What an eval is made of

**Eval**:
One folder that holds a prompt, a workspace, a scorer, and any services the agent needs.
_Avoid_: test, task, sample

**Prompt**:
The message the agent or model receives.
_Avoid_: task, input, instruction

**Workspace**:
The files the agent starts with.
_Avoid_: starter, template, seed

**Service**:
A container an eval needs next to the agent's own, such as a chain.
_Avoid_: sidecar

**Chain**:
A local Ethereum chain that runs as a service. The agent reaches it only over RPC.
_Avoid_: node

**Setup**:
An optional runnable file under `scorer/`, named `setup` or `setup.<ext>`, that prepares services before the agent starts. Its shebang selects the language. It can use the internet and return workspace files. The script never reaches the agent.

**Scorer**:
Everything that decides whether an epoch passed: a target, tests, a rubric, a check script, or several of these. It never reaches the agent.
_Avoid_: verifier

**Target**:
The expected answer to a quiz: one accepted answer, or a list where any one counts.
_Avoid_: answer key, flag

**Rubric**:
A list of yes-or-no questions a grader answers about the agent's work.
_Avoid_: criteria

**Grader**:
The model that answers a rubric.
_Avoid_: judge

**Check script**:
A runnable file under `scorer/`, named `check` or `check.<ext>`, that inspects the chain or workspace after the agent finishes. Its shebang selects the language. It can use the internet and reports named checks with `passed` and `reason` values. A script error is an eval error.

**Reference solution**:
A working answer that ships with a build or act eval. It proves the automated checks can pass.
_Avoid_: golden answer, oracle

**Motivation**:
One line on why the eval exists.
_Avoid_: notes, description

## How evals are scored

**Epoch**:
One evaluation of one agent, or one bare model, on one eval in one mode. An epoch passes only if every check passes.
_Avoid_: run, trial

**Attempt**:
A re-run of the same epoch after an error. The results row counts the initial execution as attempt 1.

**Check**:
One named thing the scorer decides about an epoch, recorded as pass or fail with a one-line reason.

**Score**:
The share of scored epochs that passed. Errors do not enter the denominator. The board shows counts, without error bars.
_Avoid_: partial score

**Eval hash**:
A fingerprint of captured file paths and bytes in an eval folder, excluding local artifacts. Results under an older hash do not describe the current eval.

**Results row**:
The latest record of one epoch: its eval, agent, mode, checks, and cost. It names the local log and links to published logs.

**Log**:
The full record of an epoch, including the transcript.
_Avoid_: trace

## How evals are grouped

**Pillar**:
The area of Ethereum an eval covers: Concepts, Transactions, Building, or Security.
_Avoid_: category, stage, track

**Type**:
What the agent does in an eval. Each supported type allows a fixed set of scorer kinds.
_Avoid_: kind

**Quiz**:
A type where the agent answers a question that has one fixed answer.

**Scenario**:
A type where the agent works through a situation, such as reviewing a contract, and writes up what it finds. Not supported yet.

**Build**:
A type where the agent writes code in its workspace.

**Act**:
A type where the agent changes chain state by sending transactions.

## What the system publishes

**Agent table**:
Scores for agents in the internet mode. The skills mode is not supported yet.

**Knowledge table**:
Scores for bare models on quizzes in the vanilla mode.

**Dataset**:
The quiz evals that run in the vanilla mode, published to Hugging Face as JSONL, one line per eval with its prompt and target.
