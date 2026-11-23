"use client";

import { checkCounts, trialScore } from "../src/scoring";
import type { EvalCell, Trial } from "../src/board";
import { percent } from "./scores";
import { updateQuery } from "./url-state";

export type TrialDisplay = "a" | "b" | "c";
export const defaultTrialDisplay: TrialDisplay = "a";
export const readTrialDisplay = (value: string | null): TrialDisplay =>
  value === "b" || value === "c" ? value : defaultTrialDisplay;
export const trialDisplayParam = (display: TrialDisplay) => display === defaultTrialDisplay ? "" : `&trial-display=${display}`;

export function TrialDisplayControl({ display }: { display: TrialDisplay }) {
  return <label className="trial-display"><span className="eyebrow">Prototype · Trial display</span>
    <select value={display} onChange={(event) => {
      const value = readTrialDisplay(event.target.value);
      updateQuery({ "trial-display": value === defaultTrialDisplay ? null : value });
    }}>
      <option value="a">A · Word at the ends</option>
      <option value="b">B · Word follows the gates</option>
      <option value="c">C · Number only</option>
    </select>
  </label>;
}

function trialScoreText(
  task: string,
  display: TrialDisplay,
  score: number,
  counts: ReturnType<typeof checkCounts>[],
) {
  if (display === "a") return score === 1 ? "passed" : score === 0 ? "failed" : percent(score);

  const gatesPassed = counts.every(({ gates }) => gates.passed === gates.total);
  if (display === "b") {
    if (score === 0) return "failed";
    return `${gatesPassed ? "passed" : "failed"} ${percent(score)}`;
  }

  const findingsPerTrial = counts[0]?.judgment.total ?? 0;
  if (task.startsWith("build/audit-") && gatesPassed && findingsPerTrial > 0 &&
      counts.every(({ judgment }) => judgment.total === findingsPerTrial)) {
    const found = counts.reduce((sum, { judgment }) => sum + judgment.passed, 0);
    return `${found} of ${counts.length * findingsPerTrial} found`;
  }
  return percent(score);
}

export function trialResult(task: string, trial: Trial, display: TrialDisplay) {
  const score = trialScore(task, trial, "gated");
  return {
    score, text: score === null ? "Error" : trialScoreText(task, display, score, [checkCounts(task, trial.checks)]),
  };
}

export function cellText(task: string, cell: EvalCell, display?: TrialDisplay) {
  if (cell.score === null) return "–";
  if (!display) return `${cell.passed}/${cell.total}`;
  const counts = cell.trials.filter((trial) => trial.status !== "error").map((trial) => checkCounts(task, trial.checks));
  return trialScoreText(task, display, cell.score, counts);
}

export function trialHint(task: string, trial: Trial) {
  if (trial.status === "error") return "Trial ended in an error";
  const missed = Object.entries(trial.checks).filter(([, check]) => !check.passed);
  if (!missed.length) return "No checks missed";
  if (missed.length === 1) {
    const name = missed[0][0].replace(/^test_/, "").replace(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ").toLowerCase();
    if (name.length <= 32) return `Missed ${name}`;
  }
  const { gates, judgment } = checkCounts(task, trial.checks);
  const gateMisses = gates.total - gates.passed, judgmentMisses = judgment.total - judgment.passed;
  return `Missed ${[
    gateMisses > 0 && `${gateMisses} gate${gateMisses === 1 ? "" : "s"}`,
    judgmentMisses > 0 && `${judgmentMisses} judgment check${judgmentMisses === 1 ? "" : "s"}`,
  ].filter(Boolean).join(" · ")}`;
}
