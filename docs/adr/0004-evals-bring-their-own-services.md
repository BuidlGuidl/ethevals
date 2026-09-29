# Evals bring their own services

An eval's optional `compose.yaml` lists only its extra services and named volumes.
The runner merges them into the stock file for that eval's type.
The runner owns `default`, `scorer`, `chain`, and the networks.
It writes stock image tags from `images/tag.py` into the merged file.
A runner image change never changes the eval hash.

Every author's service sets a positive `mem_limit` and joins only the private network.
The runner sums the merged file's memory limits before starting work.
There is no service-count cap or fixed limit for an extra service.
CI rejects privileged containers, host mounts, host namespaces, and custom builds.
Services can use declared named volumes.

The agent, scorer, and chain containers also have internet.
Check and setup scripts run inside the chain container and can read live sources.
The unfiltered Anvil RPC listens only on loopback inside that container.
The agent reaches the chain through its RPC allowlist and cannot call chain controls.

Scoring uses the compiler installed in the image.
Foundry's `offline = true` prevents compiler downloads while allowing tests to call RPC endpoints.
The runner's `foundry.toml` disables FFI and filesystem permissions during scoring.

## Considered options

- A complete compose file per eval repeats runner services and changes eval hashes whenever stock images change.
- A `chain` key in `eval.yaml` requires runner changes for each new service type.
