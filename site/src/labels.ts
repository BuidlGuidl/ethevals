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

export const scoringCopy = {
  label: "Scoring",
  names: { "all-or-nothing": "All or nothing", gated: "Gated" } satisfies Record<Scoring, string>,
  rule: {
    "all-or-nothing": "The trial score is 100% if every check passes and 0% if any check fails.",
    gated: "If any gate check fails, the trial score is 0%. If every gate check passes, divide the checks passed by all counted checks.",
  },
  entry: "The entry checks `compile`, `answered`, and `report_written` are gate checks. Leave them out of the count. Count each other gate check and judgment check once.",
  average: ["Task = mean of scored trials.", "Pillar = mean of scored tasks.", "Overall = mean of scored pillars."],
  example: {
    task: "build/token-governor",
    checks: [
      { name: "compile", label: "Compiles", passed: true },
      { name: "test_quorumCountsTheWholeSupply", label: "Quorum uses total supply", passed: true },
      { name: "test_theDelayGuardsTheMoney", label: "Two-day delay guards funds", passed: true },
      { name: "test_snapshotCanRunIt", label: "Works with Snapshot", passed: true },
      { name: "test_lateVotesExtendTheVote", label: "Late votes extend voting", passed: false },
    ],
  },
  formulas: {
    pillar: "Pillar score = mean of scored task scores. Tasks without scores are skipped.",
    eval: "Task score = mean of trial scores. Errors are excluded.",
    matrixIntro: "See each configuration’s score on each task.",
    matrixCaption: "Mean trial score for each task and configuration",
    matrixNote: "Click a task score to see its instruction and trials. Errors are excluded.",
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
