---
status: superseded by ADR-0008
---

# An eval folder declares what it needs; the runner provides it

An eval is a folder of data. `eval.yaml` holds the prompt and metadata, `workspace/` holds the agent's files, `scorer/` holds everything that grades, and an optional `compose.yaml` names the services. Only the prompt and `workspace/` reach the agent.

The scorer comes from a fixed set of kinds: a target, tests, a rubric, and a check script. The runner keeps one scorer function per kind in a registry. All grading for an eval sits under `scorer/`, never in `eval.yaml`.

A quiz's answer uses Inspect's own sample fields. `target` is one accepted answer or a list of them, and a multiple-choice quiz adds `choices`. Inspect's built-in scorers grade it: `match()`, `pattern()`, and `choice()`. The Hugging Face dataset uses the same columns, so anyone can load it into Inspect with `hf_dataset()` and no mapping.

With this shape, a team adds an eval without learning Inspect or Python, and tools can read every eval without running it.

A check script is one runnable file named `scorer/check` or `scorer/check.<ext>`. Optional setup uses `setup` or `setup.<ext>`.
The runner executes each file directly. Its shebang selects the language; Bash with `cast` or `forge` and Python are available.
Scripts receive `RPC_URL` for private chain controls and `PUBLIC_RPC_URL` for the agent's filtered RPC.
Setup finishes before the agent starts and returns only selected workspace files. Neither script reaches the agent.
Check scripts report named checks with boolean `passed` and string `reason` values. Crashes and malformed output are errors.
Reference files under `scorer/solution/` overlay the workspace, then an optional `run.sh` runs for both build and act evals.

## Considered options

- Evals written as Python code, as Inspect's own evals are: every author would have to learn the runner, and no tool could read an eval without running it.
- Our own answer matchers, such as bigint or JSON comparison: Inspect's `match()` already compares numbers with `numeric=True`, and `pattern()` pulls an answer out with a regex. A quiz that needs one exact answer format says so in its prompt.
- JSON or TOML instead of yaml: JSON has no comments and makes multi-line prompts painful. TOML works, but GitHub Actions and most tools people already touch use yaml. yaml reads `0x...` and `1.10` as numbers, so the schema requires targets and addresses to be strings.

## Parked

- A scorer written by the eval author in Python. It fits the registry as one more kind. The cost is running outside code on the CI host, which holds the API keys.
