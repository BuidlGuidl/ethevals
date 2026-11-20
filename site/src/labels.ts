import type { Agent, Layer, Mode, Pillar } from "./board";
import type { Scoring } from "./scoring";

export const names: Record<Pillar, string> = { concepts: "Concepts", build: "Build", act: "Act" };
export const layerNames: Record<Layer, string> = { contracts: "Contracts", frontend: "Frontend", backend: "Backend" };
export const modeHints: Record<Mode, string> = {
  internet: "Measures how agents do Ethereum work with web access, the way developers use them",
  skills: "Measures whether giving agents skills makes them better at Ethereum work",
  vanilla: "Measures what the model learned in training, with no web or tools",
};
export const modeNames: Record<Mode, string> = { internet: "Internet", skills: "Internet + Skills", vanilla: "Model only" };

// Every string the scoring comparison shows, in one place.
export const scoringCopy: {
  label: string; names: Record<Scoring, string>; notes: Record<Scoring, string>; examples: Record<Scoring, string>;
  comparison: string; shared: string; formulas: { pillar: string; eval: string };
} = {
  label: "Scoring",
  names: { "all-or-nothing": "All or nothing", partial: "Partial", mix: "Mixed", weighted: "Weighted" },
  notes: {
    "all-or-nothing": "A trial scores 100% if every check passes, and 0% if any check fails. This matches the live board.",
    partial: "A trial scores passed checks divided by total checks. Every check counts the same. `compile` (code compiled) and `answered` (reply was not empty) count too, so code that only compiles scores above 0%, and a wrong answer on a two-check Concepts question scores 50%.",
    mix: "Pages and audits score passed checks divided by total checks, leaving out `compile`. Contracts, backend code, onchain actions, and Concepts questions stay all or nothing. Tasks in the same pillar can follow different rules, depending on how each task is marked.",
    weighted: "Checks get 0 points for `compile` or `answered`, 1 for what the instruction asks, and 3 for the gotchas it leaves out. A trial scores points earned divided by points possible. Points are chosen per check, so scores depend on which checks get 1 point or 3.",
  },
  // One real trial under each version: token-governor with every check passed except late votes.
  examples: {
    "all-or-nothing": "Example: on `token-governor`, passing 4 of 5 checks (missing late votes) scores 0%.",
    partial: "Example: on `token-governor`, passing 4 of 5 checks (including `compile`, missing late votes) scores 4 / 5 = 80%.",
    mix: "Example: the same `token-governor` trial scores 0% because it is a contract. On `aave-savings-page`, passing 8 of 9 checks after `compile` scores 8 / 9 = 89%.",
    weighted: "Example: on `token-governor`, passing `compile` (0), standard governor (1), quorum (3), and delay (3) while missing late votes (3) scores 7 / 10 = 70%.",
  },
  comparison: "Scoring comparison on the same trials. Not the live board.",
  shared: "Each task averages its trial scores. Each pillar averages its task scores. Overall averages the pillar scores.",
  // Tooltips under the three other versions; all or nothing keeps the live board's.
  formulas: {
    pillar: "Pillar score = mean of scored task scores; tasks without scores are skipped.",
    eval: "Task score = mean of trial scores; errors are excluded.",
  },
};

const programs = new Map([
  ["claude-code", { label: "Claude Code", logo: "claude-code" }],
  ["codex", { label: "Codex", logo: "codex" }],
  ["opencode", { label: "OpenCode", logo: "opencode" }],
]);
const models = new Map([
  ["anthropic/claude-opus-5-5", "Opus 5.5"],
  ["anthropic/claude-fable-5-1", "Fable 5.1"],
  ["anthropic/claude-fable-5-2", "Fable 5.2"],
  ["openai/gpt-6.1-sol", "GPT-6.1 Sol"],
  ["openai/gpt-6-astra", "GPT-6 Astra"],
  ["openai/gpt-6.2-astra", "GPT-6.2 Astra"],
  ["openai/gpt-6.2-sol", "GPT-6.2 Sol"],
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
