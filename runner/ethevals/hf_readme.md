# ETH Evals

ETH Evals measures how well AI agents do Ethereum work and what bare models know about Ethereum.
Tasks cover knowledge questions, building apps and contracts, and acting on a chain.

Each task contains an instruction, an environment, checks, and a working solution.
You can run these folders with [Harbor](https://harborframework.com), without installing ETH Evals.

## What you need

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Docker with Compose.
Start Docker, then install Harbor:

```sh
uv tool install --python 3.13 harbor==0.24.0
```

For a task with a chain, give Docker at least 7 GiB of memory.

## Try a task without credentials

The [agent registries task](https://github.com/BuidlGuidl/ethevals/blob/main/tasks/concepts/agent-registries/README.md) asks which ERC defines registries for AI agents.
It needs no RPC URL or judge key.

Run its bundled solution:

```sh
harbor run --repo https://huggingface.co/datasets/{repo} \
  --include-task-name concepts--agent-registries \
  --agent oracle \
  --n-concurrent 1
```

`oracle` applies the solution and runs the checks.
It checks that the task works; it does not measure a real agent.
A real agent needs a model API key or plan authentication.

## Tasks that need a chain or an LLM judge

Some tasks need an RPC URL to fork a chain.
Tasks with an LLM judge also need an API key for judging.

For example, the [treasury ETH sale task](https://github.com/BuidlGuidl/ethevals/blob/main/tasks/act/treasury-eth-sale/README.md) asks an agent to write and run a quarterly sale script.
It uses both a mainnet fork at block 26,260,992 and an LLM judge.

This example uses OpenCode through OpenRouter.
Set these variables in your shell:

```sh
export MAINNET_RPC_URL='your-mainnet-rpc-url'
export ANTHROPIC_API_KEY='your-judge-api-key'
export OPENROUTER_API_KEY='your-agent-api-key'
```

The RPC provider must serve historical state at the pinned block.
The Anthropic key pays for the judge, which checks the agent's work.
The OpenRouter key pays for the agent's model calls.

Run the task:

```sh
harbor run --repo https://huggingface.co/datasets/{repo} \
  --include-task-name act--treasury-eth-sale \
  --agent opencode \
  --model openrouter/moonshotai/kimi-k3.1-pro \
  --n-concurrent 1
```

This uses your credentials and can incur API charges.
Harbor saves the results under `jobs/`.
A trial passes when its reward is 1.

## Choose your agent

For the treasury example, replace the `--agent` and `--model` options with those below.
Keep the RPC URL and judge key set.

A ChatGPT or Claude plan can pay for the agent.
It cannot pay for the judge, which still needs `ANTHROPIC_API_KEY`.

<details>
<summary>Codex with a ChatGPT plan or OpenAI API key</summary>

For a ChatGPT plan, install [Codex](https://developers.openai.com/codex/cli/).
Sign in with file storage so Harbor can copy the login into the task's container:

```sh
codex -c 'cli_auth_credentials_store="file"' login
export CODEX_AUTH_JSON_PATH="$HOME/.codex/auth.json"
export CODEX_FORCE_AUTH_JSON=YES
```

If your login file lives elsewhere, set `CODEX_AUTH_JSON_PATH` to that file.
The file must contain your ChatGPT plan login.
See [Codex authentication](https://developers.openai.com/codex/auth) for login and storage options.

Use these options:

```text
--agent codex --model openai/gpt-6-astra
```

To pay through the OpenAI API instead, clear the plan settings and set your key:

```sh
unset CODEX_FORCE_AUTH_JSON CODEX_AUTH_JSON_PATH
export OPENAI_API_KEY='your-agent-api-key'
```

</details>

<details>
<summary>Claude Code with a Claude plan or Anthropic API key</summary>

For a Claude plan, install [Claude Code](https://code.claude.com/docs/en/setup).
Create a token:

```sh
claude setup-token
```

Set the token in your shell:

```sh
export CLAUDE_CODE_OAUTH_TOKEN='your-plan-token'
export CLAUDE_FORCE_OAUTH=YES
```

`CLAUDE_FORCE_OAUTH` tells Harbor to use the plan even when the judge's Anthropic key is present.

Use these options:

```text
--agent claude-code --model anthropic/claude-opus-5-5
```

To pay through the Anthropic API instead, clear the plan settings and set your key:

```sh
unset CLAUDE_CODE_OAUTH_TOKEN CLAUDE_FORCE_OAUTH
export ANTHROPIC_API_KEY='your-api-key'
```

In this case, the Anthropic key pays for both the agent and the judge.

</details>

<details>
<summary>OpenCode with OpenRouter</summary>

Set your OpenRouter key:

```sh
export OPENROUTER_API_KEY='your-agent-api-key'
```

Use these options:

```text
--agent opencode --model openrouter/moonshotai/kimi-k3.1-pro
```

The treasury example already uses this setup.
Its Anthropic key pays for the judge separately.

</details>

## Before running another task

Browse the [task folders](https://huggingface.co/datasets/{repo}/tree/main/tasks).
Use the folder name with `--include-task-name`, such as `concepts--agent-registries`.

Read the task's README for its instruction and checks.
Then check its configuration:

- `environment/docker-compose.yaml` names any required RPC variables and the fork block.
- `[verifier.env]` in `task.toml` names the judge key, if the task needs one.

For example, the treasury task declares its [RPC requirement](https://github.com/BuidlGuidl/ethevals/blob/main/tasks/act/treasury-eth-sale/environment/docker-compose.yaml) and [judge key](https://github.com/BuidlGuidl/ethevals/blob/main/tasks/act/treasury-eth-sale/task.toml) separately.
Agent credentials are additional to these task requirements.

<details>
<summary>RPC variables from the exported folders</summary>

These names come from each task's Compose file.
Compose stops with the message if a value is missing or empty.

{requirements}

</details>

See the [Harbor guide](https://github.com/BuidlGuidl/ethevals/blob/main/docs/harbor.md) for more run options.
To write a task, read [Add a task](https://github.com/BuidlGuidl/ethevals/blob/main/docs/add-a-task.md).

Every task includes its solution, and those solutions can appear in training data.
Scores alone do not establish unseen Ethereum knowledge.
