import type { Row } from "./rows";
export type { Row } from "./rows";

export const pillars = ["concepts", "transactions", "building", "security"] as const;
export type Pillar = (typeof pillars)[number];
export type Mode = "vanilla" | "internet" | "skills";
export type TableMode = Exclude<Mode, "skills">;
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
export type DisplayEvaluation = Omit<Evaluation, "hash">;

export interface Subject {
  model: string;
  harness: string | null;
  effort: string | null;
}

export type Epoch = Pick<Row, "epoch" | "status" | "checks" | "error_kind" | "error_reason"
  | "total_tokens" | "total_seconds" | "model_cost_usd" | "grader_cost_usd"
  | "model_cost_source" | "grader_cost_source"> & {
  cost: number | null;
  issue: string;
  logUrl: string | null;
};

interface Counts {
  score: number | null;
  passed: number;
  total: number;
  errors: number;
}
export interface EvalCell extends Counts {
  state: "score" | "na" | "pending";
  epochs: Epoch[];
}
export interface PillarCell extends Counts {
  state: "score" | "empty" | "pending";
  scoredEvals: number;
}
export type Cell = EvalCell | PillarCell;
export interface PillarRow {
  evals: { id: string; cells: Record<string, EvalCell> }[];
  cells: Record<string, PillarCell>;
}
export interface Table {
  subjects: Subject[];
  pillars: Record<Pillar, PillarRow>;
}
export interface BoardData {
  sample: boolean;
  evaluations: Record<string, DisplayEvaluation>;
  tables: Record<TableMode, Table>;
}

export function subjectKey(subject: Subject): string {
  return JSON.stringify([subject.model, subject.harness, subject.effort]);
}

function evalCell(evaluation: Evaluation, mode: TableMode, rows: Row[], logBase: string): EvalCell {
  const scored = rows.filter((row) => row.status !== "error");
  const passed = scored.filter((row) => row.passed).length;
  return {
    state: !evaluation.modes.includes(mode) ? "na" : scored.length ? "score" : "pending",
    score: scored.length ? passed / scored.length : null,
    passed, total: scored.length, errors: rows.length - scored.length,
    epochs: rows.sort((a, b) => a.epoch - b.epoch).map((row) => ({
      epoch: row.epoch, status: row.status, checks: row.checks, error_kind: row.error_kind,
      error_reason: row.error_reason, total_tokens: row.total_tokens, total_seconds: row.total_seconds,
      model_cost_usd: row.model_cost_usd, grader_cost_usd: row.grader_cost_usd,
      model_cost_source: row.model_cost_source, grader_cost_source: row.grader_cost_source,
      cost: epochCost(row), issue: row.error_reason ?? Object.entries(row.checks)
        .filter(([name, check]) => name.startsWith("runner_") && name.endsWith("_limit") && !check.passed)
        .map(([, check]) => check.reason).join(" "),
      logUrl: logUrl(logBase, row.log_file),
    })),
  };
}

function pillarCell(cells: EvalCell[]): PillarCell {
  const scored = cells.filter((cell) => cell.score !== null);
  return {
    state: !cells.some((cell) => cell.state !== "na") ? "empty" : scored.length ? "score" : "pending",
    score: scored.length ? scored.reduce((sum, cell) => sum + cell.score!, 0) / scored.length : null,
    passed: cells.reduce((sum, cell) => sum + cell.passed, 0),
    total: cells.reduce((sum, cell) => sum + cell.total, 0),
    errors: cells.reduce((sum, cell) => sum + cell.errors, 0),
    scoredEvals: scored.length,
  };
}

// The loader supplies current, checked rows. Group each row and compute each cell once.
export function buildBoard(evaluations: Evaluation[], rows: Row[], sample = false, logBase = ""): BoardData {
  const groups = new Map<string, Row[]>();
  const subjects: Record<TableMode, Map<string, Subject>> = { internet: new Map(), vanilla: new Map() };
  for (const row of rows) {
    if (row.mode === "skills") continue;
    const key = subjectKey(row);
    subjects[row.mode].set(key, { model: row.model, harness: row.harness, effort: row.effort });
    const group = JSON.stringify([row.eval_id, row.mode, key]);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)!.push(row);
  }
  const tables = {} as BoardData["tables"];
  for (const mode of ["internet", "vanilla"] as const) {
    const columns = [...subjects[mode].values()].sort((a, b) => subjectKey(a).localeCompare(subjectKey(b), "en"));
    const table = { subjects: columns, pillars: {} as Table["pillars"] };
    // The knowledge table shows quizzes only. Both table and panel use these rows.
    const eligible = evaluations.filter((evaluation) => mode !== "vanilla" || evaluation.type === "quiz");
    for (const pillar of pillars) {
      const evals = eligible.filter((evaluation) => evaluation.pillar === pillar).map((evaluation) => ({
        id: evaluation.id,
        cells: Object.fromEntries(columns.map((subject) => {
          const key = subjectKey(subject);
          return [key, evalCell(evaluation, mode, groups.get(JSON.stringify([evaluation.id, mode, key])) ?? [], logBase)];
        })),
      }));
      table.pillars[pillar] = {
        evals,
        cells: Object.fromEntries(columns.map((subject) => {
          const key = subjectKey(subject);
          return [key, pillarCell(evals.map((entry) => entry.cells[key]))];
        })),
      };
    }
    tables[mode] = table;
  }
  return {
    sample, tables,
    evaluations: Object.fromEntries(evaluations.map((evaluation) => [evaluation.id, {
      id: evaluation.id, title: evaluation.title, pillar: evaluation.pillar, type: evaluation.type,
      motivation: evaluation.motivation, prompt: evaluation.prompt, choices: evaluation.choices, modes: evaluation.modes,
    }])),
  };
}

export function epochCost(row: Pick<Row, "model_cost_usd" | "grader_cost_usd">): number | null {
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
