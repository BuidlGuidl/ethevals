"use client";

import { checkCounts, checkKind, trialScore } from "../src/scoring";
import type { EvalCell, Trial } from "../src/board";
import { percent } from "./scores";

const entryLabels: Record<string, string> = {
  compile: "Did not compile", answered: "No answer", no_answer: "No answer", report_written: "No report",
};
// An entry check is only named when it fails. A passed one is not shown.
export const entryLabel = (name: string) => entryLabels[name] ?? name;

export const checkName = (name: string) =>
  name.replace(/^test_/, "").replace(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ").toLowerCase();

type State = "full" | "part" | "zero" | "error";
export type TrialSummary = { state: State; score: number | null; note: string; stopped: boolean };

// One trial in words: its score, and why when the score is 0%.
export function trialSummary(task: string, trial: Trial): TrialSummary {
  const score = trialScore(task, trial, "gated");
  if (score === null) return { state: "error", score, note: "Error", stopped: false };
  const failed = Object.entries(trial.checks).filter(([, check]) => !check.passed).map(([name]) => name);
  const entry = failed.find((name) => checkKind(task, name) === "entry");
  if (entry) return { state: "zero", score, note: entryLabel(entry), stopped: true };
  const gates = failed.filter((name) => checkKind(task, name) === "gate").map(checkName);
  if (gates.length) {
    return { state: "zero", score, note: `Gate check failed: ${gates[0]}${gates.length > 1 ? ` +${gates.length - 1}` : ""}`, stopped: true };
  }
  const { counted } = checkCounts(task, trial.checks);
  const note = counted.total ? `${counted.passed} of ${counted.total} passed` : score === 1 ? "Passed" : "Failed";
  return { state: score === 1 ? "full" : score === 0 ? "zero" : "part", score, note, stopped: false };
}

const scoreText = (summary: TrialSummary) => summary.score === null ? "Error" : percent(summary.score);
export const trialHint = (task: string, trial: Trial) => {
  const summary = trialSummary(task, trial);
  return `Trial ${trial.trial} · ${summary.score === null ? "" : `${scoreText(summary)} · `}${summary.note}`;
};
export const taskHint = (task: string, cell: EvalCell) =>
  [cell.score === null ? "No task score" : `Task score ${percent(cell.score)}`, ...cell.trials.map((trial) => trialHint(task, trial))].join("\n");

export function TrialDot({ state }: { state: State }) {
  return <span className="run-dot" data-state={state} aria-hidden="true" />;
}

export function TrialDots({ task, cell }: { task: string; cell: EvalCell }) {
  return <span className="run-dots" aria-label={cell.trials.map((trial) => trialHint(task, trial)).join(", ")}>
    {cell.trials.map((trial) => <TrialDot key={trial.trial} state={trialSummary(task, trial).state} />)}</span>;
}

export function TrialLegend() {
  return <p className="trial-legend" aria-label="Trial dot legend">
    <span><TrialDot state="full" /> 100%</span>
    <span><TrialDot state="part" /> Some checks missed</span>
    <span><TrialDot state="zero" /> 0%</span>
    <span><TrialDot state="error" /> Error</span>
  </p>;
}

export const trialScoreText = (task: string, trial: Trial) => scoreText(trialSummary(task, trial));

export function TrialScore({ task, trial }: { task: string; trial: Trial }) {
  const summary = trialSummary(task, trial);
  return <span className="trial-score"><TrialDot state={summary.state} /><span>{scoreText(summary)}</span></span>;
}

export function TrialNote({ task, trial }: { task: string; trial: Trial }) {
  const summary = trialSummary(task, trial);
  return <span className={summary.stopped ? "negative" : summary.state === "error" ? "caution" : undefined}>{summary.note}</span>;
}
