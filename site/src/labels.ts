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
// The example is one real trial. The page computes its points and scores with the board's own scoring code,
// and fills {failed}, {passed}, {total}, {sum}, {earned}, {possible} and {score} into `result`.
export const scoringCopy: {
  label: string; names: Record<Scoring, string>; comparison: string;
  parts: { rule: string; example: string; caveat: string; then: string; versions: string };
  rule: Record<Scoring, string>; detail: Partial<Record<Scoring, string[]>>; then: string;
  caveat: Record<Scoring, { lead: string; list?: string[]; close?: string }>;
  example: { title: string; task: string; checks: { name: string; label: string; passed: boolean }[]; result: Record<Scoring, string> };
  formulas: { pillar: string; eval: string; matrixIntro: string; matrixCaption: string; matrixNote: string };
} = {
  label: "Scoring",
  names: { "all-or-nothing": "All or nothing", partial: "Partial", mix: "Mixed", weighted: "Weighted" },
  comparison: "Comparison on the same trials. Not the live board.",
  parts: { rule: "Rule", example: "Example", caveat: "Keep in mind", then: "Then", versions: "This trial under each version" },
  rule: {
    "all-or-nothing": "A trial scores 100% only if every check passes. One failed check makes it 0%. This is how the live board scores.",
    partial: "Score = passed checks ÷ all checks. Every check counts the same.",
    mix: "Each task is marked one of two ways.",
    weighted: "Score = points earned ÷ points possible. Each check is worth 0, 1 or 3 points.",
  },
  detail: {
    mix: [
      "Pages and audits: passed checks ÷ all checks, with `compile` and `report_written` left out.",
      "Contracts, backend code, onchain actions and Concepts questions: all or nothing.",
    ],
    weighted: [
      "0 points: `compile`, `answered`, `report_written`.",
      "1 point: the instruction asks for it.",
      "3 points: it tests a gotcha the instruction leaves unsaid.",
    ],
  },
  caveat: {
    "all-or-nothing": { lead: "A trial that passes 4 of 5 checks scores the same as one that passes none." },
    partial: {
      lead: "Three checks only show that work was handed in:",
      list: ["`compile`: the code compiled.", "`answered`: the reply was not empty.", "`report_written`: an audit report exists."],
      close: "They count here like any other check. Code that only compiles still scores, and a wrong answer on a two-check Concepts task scores 50%.",
    },
    mix: { lead: "Two tasks in the same pillar can follow different rules." },
    weighted: { lead: "The points are a judgement call for each check. Move a check from 1 point to 3 and the scores change." },
  },
  then: "A task's score is the average of its trials. A pillar's score is the average of its tasks. Overall is the average of the three pillars.",
  example: {
    title: "Fable 5.2 on `token-governor`, one trial",
    task: "build/token-governor",
    checks: [
      { name: "compile", label: "Compiles", passed: true },
      { name: "test_snapshotCanRunIt", label: "Standard governor, works with Snapshot", passed: true },
      { name: "test_quorumCountsTheWholeSupply", label: "Quorum counts the whole supply", passed: true },
      { name: "test_theDelayGuardsTheMoney", label: "Two-day delay guards the money", passed: true },
      { name: "test_lateVotesExtendTheVote", label: "Late votes extend the vote", passed: false },
    ],
    result: {
      "all-or-nothing": "{failed} check failed, so {score}.",
      partial: "{passed} of {total} checks passed = {score}.",
      mix: "`token-governor` is a contract, so all or nothing: {score}. A page trial that passes 8 of 9 checks scores 89%.",
      weighted: "{sum} = {earned} of {possible} points = {score}.",
    },
  },
  // Tooltips and task matrix text under the three other versions; all or nothing keeps the live board's.
  formulas: {
    pillar: "Pillar score = mean of scored task scores; tasks without scores are skipped.",
    eval: "Task score = mean of trial scores; errors are excluded.",
    matrixIntro: "A detailed view of the Leaderboard. See each agent's score on every task, grouped by pillar.",
    matrixCaption: "Mean trial score for each task and configuration",
    matrixNote: "Mean trial score per task. Tasks with one check show trials passed. Click a scored cell for its instruction and trials. Errors are excluded.",
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
