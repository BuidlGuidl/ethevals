export const pillars = ["concepts", "transactions", "building", "security"] as const;
export type Pillar = (typeof pillars)[number];
export type Mode = "vanilla" | "internet" | "skills";
export type EvalType = "quiz" | "scenario" | "build" | "act";

export interface Evaluation {
  id: string;
  hash: string;
  title: string;
  pillar: Pillar;
  type: EvalType;
  motivation: string;
  prompt: string;
  choices: string[];
  modes: Mode[];
}

export interface Subject {
  model: string;
  harness: string | null;
  effort: string | null;
}

export interface Row extends Subject {
  schema_version: 2;
  eval_id: string;
  eval_hash: string;
  pillar: Pillar;
  type: EvalType;
  mode: Mode;
  answer_kind: string | null;
  epoch: number;
  status: "passed" | "failed" | "error";
  passed: boolean | null;
  checks: Record<string, { passed: boolean; reason: string }>;
  error_kind: string | null;
  error_reason: string | null;
  total_tokens: number;
  token_source: string;
  model_cost_usd: number | null;
  grader_cost_usd: number | null;
  model_cost_source: string;
  grader_cost_source: string;
  total_seconds: number | null;
  working_seconds: number | null;
  log_file: string;
}

export interface BoardData {
  sample: boolean;
  evaluations: Evaluation[];
  rows: Row[];
  logBase: string;
}

export interface Cell {
  state: "score" | "na" | "pending";
  score: number | null;
  passed: number;
  total: number;
  errors: number;
  scoredEvals: number;
  epochs: Row[];
}

export function subjectKey(subject: Subject): string {
  return JSON.stringify([subject.model, subject.harness, subject.effort]);
}

export function boardRows(evaluations: Evaluation[], rows: Row[]): Row[] {
  const current = new Map(evaluations.map((evaluation) => [evaluation.id, evaluation]));
  return rows.filter((row) => {
    const evaluation = current.get(row.eval_id);
    return row.answer_kind === null && row.token_source !== "mock"
      && evaluation?.hash === row.eval_hash && evaluation.modes.includes(row.mode)
      && evaluation.type === row.type && evaluation.pillar === row.pillar
      && (row.mode === "internet" ? Boolean(row.harness)
        : row.mode === "vanilla" && row.harness === null && evaluation.type === "quiz");
  });
}

export function subjectsFor(rows: Row[], mode: Mode): Subject[] {
  const subjects = new Map<string, Subject>();
  for (const row of rows.filter((row) => row.mode === mode)) {
    subjects.set(subjectKey(row), { model: row.model, harness: row.harness, effort: row.effort });
  }
  return [...subjects.values()].sort((a, b) => subjectKey(a).localeCompare(subjectKey(b), "en"));
}

export function evalCell(evaluation: Evaluation, subject: Subject, mode: Mode, rows: Row[]): Cell {
  const applicable = evaluation.modes.includes(mode);
  const epochs = applicable ? boardRows([evaluation], rows)
    .filter((row) => row.mode === mode && subjectKey(row) === subjectKey(subject))
    .sort((a, b) => a.epoch - b.epoch) : [];
  const scored = epochs.filter((row) => row.status !== "error" && row.passed !== null);
  const passed = scored.filter((row) => row.passed).length;
  return {
    state: !applicable ? "na" : scored.length ? "score" : "pending",
    score: scored.length ? passed / scored.length : null,
    passed,
    total: scored.length,
    errors: epochs.filter((row) => row.status === "error").length,
    scoredEvals: scored.length ? 1 : 0,
    epochs,
  };
}

export function pillarCell(evaluations: Evaluation[], subject: Subject, mode: Mode, rows: Row[]): Cell {
  const cells = evaluations.map((evaluation) => evalCell(evaluation, subject, mode, rows));
  const scored = cells.filter((cell) => cell.score !== null);
  return {
    state: !cells.some((cell) => cell.state !== "na") ? "na" : scored.length ? "score" : "pending",
    score: scored.length ? scored.reduce((sum, cell) => sum + cell.score!, 0) / scored.length : null,
    passed: cells.reduce((sum, cell) => sum + cell.passed, 0),
    total: cells.reduce((sum, cell) => sum + cell.total, 0),
    errors: cells.reduce((sum, cell) => sum + cell.errors, 0),
    scoredEvals: scored.length,
    epochs: cells.flatMap((cell) => cell.epochs),
  };
}

export function epochCost(row: Row): number | null {
  return row.model_cost_usd === null || row.grader_cost_usd === null
    ? null : row.model_cost_usd + row.grader_cost_usd;
}

export function logUrl(base: string, file: string): string | null {
  if (!base || !file || file.startsWith("/") || file.includes("\\")
    || file.split("/").some((part) => part === ".." || part === ".")
    || /^[a-z][a-z\d+.-]*:/i.test(file)) return null;
  const encoded = file.split("/").map(encodeURIComponent).join("/");
  return `${base.replace(/\/$/, "")}/${encoded}`;
}
