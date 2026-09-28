# Evals bring their own services

An eval that needs more than the agent's own container ships a `compose.yaml`. The anvil chain is the first shared image. A team whose task needs a validator, a database, or an indexer adds it the same way, with no change to the runner. An eval without `compose.yaml` gets the stock file for its type.

Every `compose.yaml` follows the same rules:

- The agent's service is named `default`.
- The agent, the scorer, and the other services share a private network. Only the agent and the scorer also have internet.
- The scorer has internet so Forge can fetch the compiler that matches the agent's `pragma`. It uses our `foundry.toml` with `ffi = false`, so the agent's code can't run shell commands during scoring.
- CI rejects `privileged` containers and host mounts, because outside teams' files run in our CI.

Inspect passes one compose file per eval, so each eval's file is complete, copied from a template. It can't extend a shared base.

## Considered options

- Anvil built into the runner, declared as `chain:` in `eval.yaml`: a smaller format, but any service besides a chain would need a runner change.
