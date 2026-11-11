---
status: accepted
---

# Judges use agents and the Claude plan

Code that reads page wording or known transaction shapes has failed correct work.
A saved swap page failed three checks when the clicking script could not follow its controls or read its amounts.
A saved treasury sale put its minimum on the last sale step, which the calldata reader did not recognize.

## The decision

- Every judge uses RewardKit's `claude-code` agent judge, Opus 5.5, high effort, and `guard = "flag"`.
- The Claude plan pays through `CLAUDE_CODE_OAUTH_TOKEN`.
  Results still record the API price of the judge's calls.
  Plan-paid judges reserve no API spend, like plan-paid agents.
- Browser judges use pinned Playwright MCP tools and the built page.
  They also get source, a funded wallet, chain reads through `cast`, and small commands for test conditions.
  Every transaction comes from the page.
- The judge starts one folder above the submitted code.
  Its starting folder contains no submitted instructions, settings, or MCP configuration.
- Criteria remain short yes-or-no questions.
  A page the judge cannot use gets no.
  A judge crash or timeout produces an error and no reward.
- Code keeps checks that read exact chain facts.
  On the swap page, those checks read every transaction from the judge's wallet session after the judge finishes.
- The treasury sale's minimum and deadline become criteria.
  Its other four code checks and two criteria keep their meaning.
- File-reading judges read their inputs inside their starting folder.
  They keep their existing criteria and prompt wording.
- The free check uses no judge.
  The swap solution gets a small walk-through that knows its controls and never runs on submitted pages.

The judge gets user-level settings for read-only `cast` commands and the task's helper commands.
Background tasks are disabled so a hung shell command cannot keep a finished judge alive.
The Playwright allow list excludes the tool that runs code in the MCP process.
Tests install pinned Claude Code and Playwright MCP after the agent finishes.
The browser judge uses Chromium already present in the page image.
Judge tools never enter shared image inputs or a task's environment folder.
Instructions, environment hashes, image pins, and artifact settings stay unchanged.
Harbor 0.24.0 and RewardKit 0.2.3 remain pinned.
The version upgrade waits for a separate change because it would change shared image pins.

Build commands and submitted processes receive no judge credentials.
The verifier receives the plan token only after the agent stops.
Publication checks scan for that token, like every other declared secret.
Shared verifiers retain the container isolation gap documented in ADR 0011.

This decision changes no trial identity or hash rules.
The judge program joins its model and effort in results and the existing judge settings fingerprint.
The Aave savings page's browser checks follow in a separate change.
Another change owns its existing file-reading judges and plan payment.

The treasury judge reads saved script source, transaction calldata, and receipt logs.
It receives no live chain endpoint or shell permission for chain reads.
New trials and regrades use the same saved evidence.

## Interim regrade rule

A judge that declares MCP servers needs a live session.
A judge-only change on such a task reruns its trials instead of regrading saved inputs.
File-reading agent judges keep judge-only regrades.
Their saved input copies and content fingerprints decide whether a judge answer can be reused.
This rule stays separate from identity and hash rules so saved-chain replay can replace it later.

## Considered options

- Keep the clicking script and add words to its readers.
  Each accepted control or number format leaves another valid page that the readers cannot follow.
- Require fixed button names in the instruction.
  That measures compliance with the clicking script instead of the requested page.
- Give the judge source alone.
  Source cannot prove what the running page does with the wallet and chain.
- Add a second model that clicks but never decides.
  Parsing its observations puts page wording back under code's rules.

## Changes to earlier decisions

This replaces ADR 0011's model-only judge and API-key payment rules.
It replaces ADR 0014's judge transport and payment rules while keeping the voting page's criteria.
It replaces ADR 0016's judge transport and payment rules while keeping Concepts criteria and final-reply inputs.
