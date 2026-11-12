---
status: accepted
---

# Public tasks select their judge credential

A published task must run with Docker and Harbor without an ETH Evals install.
A person can have an Anthropic API key without a Claude plan token.
The board still pays for its judges through the plan.

## The decision

Each judged task declares both credentials as optional verifier inputs.
Its tests select the plan token when both are set.
With only an API key, the tests pass that key to the same Claude Code agent judge.
The judge receives only the selected credential.
A board run still requires the plan token and disables API fallback through its existing overrides.

With neither credential, verification stops before tool installation or judge execution.
It writes no score and gives one line naming both credential variables.
The task saves that line in its verifier logs and `judge-error.txt`.
Unjudged tasks and the runner's explicit free checks keep their model-free path.
Cached regrades can reuse saved answers without a credential.

The credential helper lives in each task's tests.
It imports no runner code and uses no host checkout files.
The helper copies share one rule, covered by a byte-comparison test and launcher behavior tests.
Instructions, environments, image pins, and artifact settings stay unchanged.
The judge program, model, effort, and criteria also stay unchanged.

## Considered options

- Require the Claude plan for every public user.
  This excludes API-key users even though the judge supports their credential.
- Let the board fall back to API billing.
  This can spend API money when the intended plan credential is missing.
- Return a passing score without a judge credential.
  That would claim that unchecked criteria passed.
