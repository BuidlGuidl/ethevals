import type { Agent, Mode, Pillar } from "./board";

export const names: Record<Pillar, string> = { concepts: "Concepts", transactions: "Transactions", building: "Building", security: "Security" };
export const modeNames: Record<Mode, string> = { internet: "Internet", skills: "Internet + Skills", vanilla: "Model only" };

const harnesses = new Map([
  ["claude_code", "Claude Code"],
  ["codex_cli", "Codex"],
  ["opencode", "OpenCode"],
]);
const models = new Map([
  ["anthropic/claude-opus-5-5", "Opus 5.5"],
  ["openai/gpt-5.5", "GPT-5.5"],
  ["openrouter/moonshotai/kimi-k3", "Kimi K3"],
  ["openrouter/z-ai/glm-5.3", "GLM 5.3"],
]);
export const modelLabel = (id: string) => models.get(id) ?? id;
export const harnessLabel = (id: string) => harnesses.get(id) ?? id;
export const agentLabel = (agent: Agent) => agent.harness
  ? `${harnessLabel(agent.harness)} / ${modelLabel(agent.model)}` : modelLabel(agent.model);
export const agentDetails = (agent: Agent) => [agent.model, agent.harness, `effort ${agent.effort ?? "provider default"}`].filter(Boolean).join(" · ");
