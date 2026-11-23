import type { Eval } from "./board";
import type { Row } from "./rows";

export const checkKinds = ["gate", "judgment"] as const;
export type CheckTags = Record<string, (typeof checkKinds)[number]>;

const entryChecks = new Set(["compile", "answered", "no_answer", "report_written"]);
type ScoringTask = Pick<Eval, "pillar" | "checks">;

export function checkKind(task: ScoringTask, name: string): "entry" | "concept" | "gate" | "judgment" | undefined {
  if (entryChecks.has(name)) return "entry";
  if (task.pillar === "concepts") return "concept";
  return task.checks && Object.hasOwn(task.checks, name) ? task.checks[name] : undefined;
}

type Stop = { kind: "entry"; name: string } | { kind: "gate"; name: string; more: number };
export type TrialScore = { value: null } | { value: number; passed: number; total: number; stop: Stop | null };

export function scoreTrial(task: ScoringTask, trial: Pick<Row, "status" | "checks">): TrialScore {
  if (trial.status === "error") return { value: null };
  let passed = 0, total = 0;
  let failedEntry: string | undefined;
  const failedGates: string[] = [];
  for (const [name, check] of Object.entries(trial.checks)) {
    const kind = checkKind(task, name);
    if (kind === undefined) continue;
    if (kind === "entry") {
      if (!check.passed) failedEntry ??= name;
      continue;
    }
    total++;
    if (check.passed) passed++;
    else if (kind === "gate") failedGates.push(name);
  }
  const [firstGate, ...otherGates] = failedGates;
  const stop: Stop | null = failedEntry ? { kind: "entry", name: failedEntry }
    : firstGate !== undefined ? { kind: "gate", name: firstGate, more: otherGates.length } : null;
  let value = Number(trial.status === "passed");
  if (stop) value = 0;
  else if (total) value = task.pillar === "concepts" ? Number(passed === total) : passed / total;
  return { value, passed, total, stop };
}
