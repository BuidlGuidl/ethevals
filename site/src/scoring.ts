import type { Row } from "./rows";
import { taskScoring } from "./scoring-settings";

// Four ways to score one trial, compared on the same rows. A task, pillar, and Overall average as before.
export const scorings = ["all-or-nothing", "partial", "mix", "weighted"] as const;
export type Scoring = (typeof scorings)[number];
export const defaultScoring: Scoring = "all-or-nothing";
export const readScoring = (value: string | null): Scoring => scorings.find((scoring) => scoring === value) ?? defaultScoring;

// Nothing else can pass without an entry check, and passing one alone is no work.
const entryChecks = new Set(["compile", "answered", "report_written"]);
// The runner writes this check alone when a model gave no answer twice; it scores 0 like any failed check.
const noAnswer = "no_answer";

const isPartial = (task: string) => task in taskScoring ? taskScoring[task].partial === true : task.startsWith("build/audit-");

// Points for each check under a version, or null when the trial scores all or nothing.
export function checkPoints(task: string, checks: string[], scoring: Scoring): Record<string, number> | null {
  if (scoring === "all-or-nothing" || (scoring === "mix" && !isPartial(task))) return null;
  const settings = taskScoring[task];
  return Object.fromEntries(checks.map((check) => [check,
    scoring === "partial" ? 1
      : entryChecks.has(check) ? 0
      : scoring === "weighted" && settings?.three.includes(check) ? 3 : 1]));
}

// A trial's score from 0 to 1. With no points possible it falls back to all or nothing.
export function trialScore(task: string, trial: Pick<Row, "status" | "checks">, scoring: Scoring): number {
  const allOrNothing = trial.status === "passed" ? 1 : 0;
  const points = checkPoints(task, Object.keys(trial.checks), scoring);
  if (!points) return allOrNothing;
  const possible = Object.values(points).reduce((sum, value) => sum + value, 0);
  const earned = Object.entries(points).reduce((sum, [check, value]) => sum + (trial.checks[check].passed ? value : 0), 0);
  return possible ? earned / possible : allOrNothing;
}

// A typo in the settings would silently change scores, so the build checks them against current rows.
export function checkScoringSettings(rows: Pick<Row, "task_id" | "checks">[]): void {
  for (const [task, settings] of Object.entries(taskScoring)) {
    const taskRows = rows.filter((row) => row.task_id === task);
    if (!taskRows.length) continue;
    const seen = new Set(taskRows.flatMap((row) => Object.keys(row.checks)));
    const listed = new Set([...settings.one, ...settings.three]);
    for (const check of listed) {
      if (!seen.has(check)) throw new Error(`Scoring settings for ${task} name ${check}, which no current row has.`);
    }
    for (const check of seen) {
      if (!listed.has(check) && !entryChecks.has(check) && check !== noAnswer) {
        throw new Error(`Scoring settings for ${task} do not list its check ${check}.`);
      }
    }
  }
}
