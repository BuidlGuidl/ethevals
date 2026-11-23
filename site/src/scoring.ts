import type { Row } from "./rows";
import { checkLabels } from "./scoring-settings";

export const scorings = ["all-or-nothing", "gated"] as const;
export type Scoring = (typeof scorings)[number];
export const defaultScoring: Scoring = "all-or-nothing";
export const readScoring = (value: string | null): Scoring => value === "gated" ? value : defaultScoring;

const entryChecks = new Set(["compile", "answered", "report_written"]);
export function checkKind(task: string, name: string): "entry" | "gate" | "judgment check" {
  return entryChecks.has(name) ? "entry" : checkLabels.get(`${task}|${name}`) ?? "judgment check";
}

export function checkCounts(task: string, checks: Row["checks"]) {
  const counts = {
    entry: { passed: 0, total: 0 },
    gate: { passed: 0, total: 0 },
    "judgment check": { passed: 0, total: 0 },
  };
  for (const [name, check] of Object.entries(checks)) {
    const count = counts[checkKind(task, name)];
    count.total++;
    if (check.passed) count.passed++;
  }
  const judgment = counts["judgment check"];
  const gates = { passed: counts.entry.passed + counts.gate.passed, total: counts.entry.total + counts.gate.total };
  return {
    gates, judgment,
    counted: { passed: counts.gate.passed + judgment.passed, total: counts.gate.total + judgment.total },
  };
}

export function trialScore(task: string, trial: Pick<Row, "status" | "checks">, scoring: Scoring): number | null {
  if (trial.status === "error") return null;
  const allOrNothing = trial.status === "passed" ? 1 : 0;
  if (scoring === "all-or-nothing") return allOrNothing;
  const { gates, counted } = checkCounts(task, trial.checks);
  if (gates.passed < gates.total) return 0;
  return counted.total ? counted.passed / counted.total : allOrNothing;
}
