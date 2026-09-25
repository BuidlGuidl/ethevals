# ETH Evals

ETH Evals measures how well AI agents handle Ethereum work across concepts, transactions, building and security, and tracks what bare models know about Ethereum. This file is the shared vocabulary for writing and running evals.

## Who we evaluate

**Agent**:
A harness paired with a model. The `internet` and `skills` modes score agents, because that is what people use day to day.
_Avoid_: model (when you mean the thing under test)

**Harness**:
The program that drives the model: its tools, its system prompt, its loop. Examples: Claude Code, Codex, pi.

**Mode**:
What the model or agent can reach during a run. Each eval lists the modes it runs in. The names may change.

**Vanilla**:
A mode where the bare model answers a straight question, with no harness, no tools, and no agent loop. Its results go in a separate knowledge table, because they measure what a model knows rather than what an agent can do.

**Internet**:
A mode where the agent works as it normally would: the web, a shell, its workspace, and a chain if the eval asks for one. No Ethereum skills are installed.

**Skills**:
The `internet` mode plus Ethereum skills.

## What an eval is made of

**Eval**:
One folder that holds a prompt, the world the agent starts in, and a grader.
_Avoid_: test, task

**Prompt**:
The message the agent receives, written in the eval's `eval.yaml`.
_Avoid_: task, input, instruction

**Starter**:
The files copied into the agent's workspace before a run.
_Avoid_: template, seed

**Setup**:
An optional script that prepares the chain before the agent starts. It never reaches the agent.

**Grader**:
Everything that decides whether a run passed: an answer file, a rubric, hidden tests, a chain check script, or several of these. It never reaches the agent.
_Avoid_: scorer, verifier

**Chain**:
A local Ethereum chain an eval asks for in `eval.yaml`, either fresh or forked at a pinned block. It runs apart from the agent, which reaches it only at `$RPC_URL`. Test-only cheat methods are blocked.
_Avoid_: node

**Rubric**:
A list of yes-or-no checks an LLM judge answers about the agent's work.
_Avoid_: criteria

**Motivation**:
One line on why the eval exists.
_Avoid_: notes, description

## How evals are scored

**Run**:
One attempt by one agent, or one bare model, at one eval in one mode. A run passes only if every check passes.

**Check**:
One named thing a grader decides about a run, recorded as pass or fail with a one-line reason.

**Score**:
The share of runs that passed, shown with an error bar that comes from repeating runs.
_Avoid_: partial score

## How evals are grouped

**Pillar**:
The area of Ethereum an eval covers: Concepts, Transactions, Building, or Security.
_Avoid_: category, stage, track

**Type**:
What the agent does in an eval. It says nothing about how the eval is graded.
_Avoid_: kind

**Quiz**:
A type where the agent answers a question that has one fixed answer.

**Scenario**:
A type where the agent works through a situation, such as reviewing a contract, and writes up what it finds.

**Build**:
A type where the agent writes code in its starter workspace.

**Act**:
A type where the agent changes chain state by sending transactions.
