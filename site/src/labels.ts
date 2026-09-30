import type { Agent } from "./board";

const harnesses = new Map([
  ["claude_code", { label: "Claude Code", logo: "claude-code" }],
  ["codex_cli", { label: "Codex", logo: "codex" }],
  ["opencode", { label: "OpenCode", logo: "opencode" }],
]);
const models = new Map([
  ["anthropic/claude-opus-5-5", "Opus 5.5"],
  ["openai/gpt-5.5", "GPT-5.5"],
  ["openrouter/moonshotai/kimi-k3", "Kimi K3"],
  ["openrouter/z-ai/glm-5.3", "GLM 5.3"],
]);
const providers = new Map([
  ["anthropic", "claude"], ["openai", "openai"], ["openrouter", "openrouter"],
]);

export const modelLabel = (id: string) => models.get(id) ?? id;
export const harnessLabel = (id: string) => harnesses.get(id)?.label ?? id;
export const agentLabel = (agent: Agent) => agent.harness
  ? `${harnessLabel(agent.harness)} / ${modelLabel(agent.model)}` : modelLabel(agent.model);
export const agentDetails = (agent: Agent) => [agent.model, agent.harness, `effort ${agent.effort ?? "provider default"}`].filter(Boolean).join(" · ");
export const agentLogo = (agent: Agent) => agent.harness
  ? harnesses.get(agent.harness)?.logo
  : models.has(agent.model) ? providers.get(agent.model.split("/")[0]) : undefined;
