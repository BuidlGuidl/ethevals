---
status: accepted
---

# Raise OpenCode's output limit until Harbor runs OpenCode 2

OpenCode 1.x limits each model call to 32,000 output tokens, whatever the model allows.
GLM 5.3 at high effort can spend all of it thinking, and the call then ends with no reply, so the trial fails on our setup and not on the task.
OpenRouter allows both open models 943,718 output tokens.
OpenCode 2 drops the limit, but Harbor 0.24.0, and Harbor's main branch, install only OpenCode 1.x.
So until Harbor runs OpenCode 2, the job config raises the limit with OpenCode's own setting.

## The setting

- **Both OpenCode agents set `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` to 131,072.** Kimi gets it too, so the two open models run under the same limit.
- **131,072 leaves room for the conversation.** OpenCode keeps the output limit free when it decides to compact, so 131,072 leaves about 917k of the 1M-token context. The full 943,718 would leave about 105k and compact long trials early.
- **The value is written `+131072`.** Harbor 0.24.0 treats a setting whose name contains TOKEN as a secret, and replaces its value in every trial file once the trial ends. A bare 131072 would be replaced inside longer numbers too, which can break a trajectory or Harbor's result JSON. A plus sign never appears inside a JSON number or in hex. OpenCode reads both forms as 131,072, and a value it can't read falls back to 32,000.
- **Our secret check ignores it.** The check skips values shorter than 8 bytes, so it doesn't withhold trials that contain `+131072`.
- **It lives in the job config, not a local `.env`.** CI never reads `.env`, so local and CI trials would differ.

A stub server in place of OpenRouter showed what OpenCode 1.18.33 sends for GLM: `max_tokens` is 32,000 without the setting and 131,072 with it, and the rest of the request settings, high reasoning effort included, stay the same.

## Results already recorded

- **No recorded trial reruns.** The setting isn't part of a trial's identity.
- **No Kimi or GLM result on the board ended at the limit.** The one failed GLM trial missed a rounding check.
- **Trials on open pull requests that ended at the limit are rerun there.**

## When Harbor runs OpenCode 2

Remove the setting and upgrade OpenCode in the same change. That upgrade changes the agent's version and its command, so it gets its own decision.

## Considered options

- **Upgrade to OpenCode 2 now.** It ships as a separate npm package, `@opencode/cli`, and its `run` command takes different flags, so Harbor's OpenCode agent can't start it. Our own agent would carry a new agent name, and the name is part of every OpenCode trial's identity, so all of them would rerun.
- **Lower GLM's effort.** Less thinking would fit under 32,000, but the board runs every model at high effort.
- **Set it in `.env`.** Only the Mac reads that file.
