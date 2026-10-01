---
status: accepted
---

# Hash the skills pack separately from the eval

The eval hash covers only files in the eval folder.
The skills pack has its own hash, computed from the captured pack files.
A CLI command captures the pack once and shares that snapshot across its evals.

An epoch records the pack hash as `skills_hash` in skills mode.
Internet and vanilla epochs record `skills_hash: null`.
Epoch identity includes this field alongside the eval hash, actor, mode, effort, and epoch number.

A skills change reruns only skills-mode epochs.
An eval file change reruns every mode for that eval.
Planning and result folding use the same identity as execution.

Rows use schema version 6.
The catalog records the current pack hash once beside its eval list.
The board shows rows with the current eval hash and, in skills mode, the current pack hash.
The board skips older row schemas.

Scorers, container preparation, and HF exports keep the eval hash as their eval key.
Skills mode installs the same captured skill files as before.
This decision changes result identity without changing what the agent receives.

The change retires the previous row schema.
Existing rows remain stored, and the next plan lists the current identities as missing.
