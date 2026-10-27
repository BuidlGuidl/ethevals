import type { Agent, Mode, Pillar } from "./board";

export const names: Record<Pillar, string> = { concepts: "Concepts", build: "Build", act: "Act" };
export const modeHints: Record<Mode, string> = {
  internet: "Measures how agents do Ethereum work with web access, the way developers use them",
  skills: "Measures whether giving agents skills makes them better at Ethereum work",
  vanilla: "Measures what the model learned in training, with no web or tools",
};
export const modeNames: Record<Mode, string> = { internet: "Internet", skills: "Internet + Skills", vanilla: "Model only" };

const programs = new Map([
  ["claude-code", { label: "Claude Code", logo: "claude-code" }],
  ["codex", { label: "Codex", logo: "codex" }],
  ["opencode", { label: "OpenCode", logo: "opencode" }],
]);
const models = new Map([
  ["anthropic/claude-opus-5-5", "Opus 5.5"],
  ["anthropic/claude-fable-5-1", "Fable 5.1"],
  ["openai/gpt-6.1-sol", "GPT-6.1 Sol"],
  ["openai/gpt-6-astra", "GPT-6 Astra"],
  ["openrouter/moonshotai/kimi-k3.1-pro", "Kimi K3.1 Pro"],
  ["openrouter/z-ai/glm-5.3", "GLM 5.3"],
  ["openrouter/deepseek/deepseek-v4.1-flash-1017", "DeepSeek V4.1 Flash"],
  ["openrouter/x-ai/grok-4.7", "Grok 4.7"],
  ["openrouter/google/gemini-4-argon", "Gemini 4 Argon"],
]);
const providers = new Map([
  ["anthropic", "claude"], ["openai", "openai"], ["openrouter", "openrouter"],
]);

// Join hard wraps for display; keep blank lines and list items.
export const unwrapPrompt = (text: string) => text.trimEnd().replace(/(\S)\n(?!\n|\s|[-*•]\s|\d+[.)]\s)/g, "$1 ");
export const modelLabel = (id: string) => models.get(id) ?? id;
export const programLabel = (id: string) => programs.get(id)?.label ?? id;
export const agentLabel = (agent: Agent) => agent.agent
  ? `${programLabel(agent.agent)} / ${modelLabel(agent.model)}` : modelLabel(agent.model);
export const agentDetails = (agent: Agent) => [agent.model, agent.agent, `effort ${agent.effort ?? "provider default"}`].filter(Boolean).join(" · ");
export const modelLogo = (id: string) => providers.get(id.split("/")[0]);
export const agentLogo = (agent: Agent) => agent.agent
  ? programs.get(agent.agent)?.logo : modelLogo(agent.model);
