import type { Row } from "./rows";
export type { Row } from "./rows";

export const pillars = ["concepts", "transactions", "building", "security"] as const;
export type Pillar = (typeof pillars)[number];
export type Mode = "vanilla" | "internet" | "skills";

export interface Eval {
  id: string;
  hash: string;
  title: string;
  pillar: Pillar;
  motivation: string;
  prompt: string;
  choices: string[];
  modes: Mode[];
}
export type DisplayEval = Omit<Eval, "hash">;

export interface Agent {
  model: string;
  harness: string | null;
  effort: string | null;
}

export type Epoch = Pick<Row, "epoch" | "status" | "checks" | "error_kind" | "error_reason"
  | "total_tokens" | "total_seconds" | "model_cost_usd" | "grader_cost_usd"
  | "cost_source" | "limit"> & {
  cost: number | null;
  issue: string;
  logUrl: string | null;
  logHref?: string | null;
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
  agents: Agent[];
  pillars: Record<Pillar, PillarRow>;
  summaries: Record<string, ConfigurationSummary>;
}
export interface ConfigurationSummary {
  scores: Record<Pillar | "overall", number | null>;
  costPerPass: number | null;
  medianTokens: number | null;
  passed: number;
  total: number;
  errors: number;
}
export interface BoardData {
  demo: boolean;
  evaluations: Record<string, DisplayEval>;
  tables: Record<Mode, Table>;
  lifts: Record<string, Record<Pillar | "overall", number | null>>;
  counts: { evals: number; agents: number; runs: number };
}

export function overallScore(scores: (number | null)[]): number | null {
  const scored = scores.filter((score): score is number => score !== null);
  return scored.length ? scored.reduce((sum, score) => sum + score, 0) / scored.length : null;
}

export function costPerPass(epochs: Pick<Epoch, "status" | "model_cost_usd">[]): number | null {
  const scored = epochs.filter((epoch) => epoch.status !== "error");
  const passed = scored.filter((epoch) => epoch.status === "passed").length;
  if (!passed || scored.some((epoch) => epoch.model_cost_usd === null)) return null;
  return scored.reduce((sum, epoch) => sum + epoch.model_cost_usd!, 0) / passed;
}

export function skillLift(skills: number | null, internet: number | null): number | null {
  return skills === null || internet === null ? null : (skills - internet) * 100;
}

function median(values: (number | null)[]): number | null {
  const sorted = values.filter((value): value is number => value !== null).sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length ? sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2 : null;
}

export function agentKey(agent: Agent): string {
  return JSON.stringify([agent.model, agent.harness, agent.effort]);
}

function evalCell(evaluation: Eval, mode: Mode, rows: Row[]): EvalCell {
  const scored = rows.filter((row) => row.status !== "error");
  const passed = scored.filter((row) => row.status === "passed").length;
  return {
    state: !evaluation.modes.includes(mode) ? "na" : scored.length ? "score" : "pending",
    score: scored.length ? passed / scored.length : null,
    passed, total: scored.length, errors: rows.length - scored.length,
    epochs: rows.sort((a, b) => a.epoch - b.epoch).map((row) => ({
      epoch: row.epoch, status: row.status, checks: row.checks, error_kind: row.error_kind,
      error_reason: row.error_reason, total_tokens: row.total_tokens, total_seconds: row.total_seconds,
      model_cost_usd: row.model_cost_usd, grader_cost_usd: row.grader_cost_usd,
      cost_source: row.cost_source,
      limit: row.limit,
      cost: epochCost(row), issue: row.error_reason ?? (row.limit
        ? [...new Set(Object.values(row.checks).filter((check) => !check.passed).map((check) => check.reason))].join(" ")
        : ""),
      logUrl: row.log_url,
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
export function buildBoard(evaluations: Eval[], rows: Row[], demo = false): BoardData {
  const groups = new Map<string, Row[]>();
  const agents: Record<Mode, Map<string, Agent>> = { internet: new Map(), skills: new Map(), vanilla: new Map() };
  for (const row of rows) {
    const key = agentKey(row);
    agents[row.mode].set(key, { model: row.model, harness: row.harness, effort: row.effort });
    const group = JSON.stringify([row.eval_id, row.mode, key]);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)!.push(row);
  }
  const tables = {} as BoardData["tables"];
  const configurations = new Map([...agents.internet, ...agents.skills]);
  for (const mode of ["internet", "skills", "vanilla"] as const) {
    const columns = [...(mode === "vanilla" ? agents.vanilla : configurations).values()]
      .sort((a, b) => agentKey(a).localeCompare(agentKey(b), "en"));
    const table: Table = { agents: columns, pillars: {} as Table["pillars"], summaries: {} };
    // The knowledge table shows declared vanilla evals. Both table and panel use these rows.
    const eligible = evaluations.filter((evaluation) => mode !== "vanilla" || evaluation.modes.includes("vanilla"));
    for (const pillar of pillars) {
      const evals = eligible.filter((evaluation) => evaluation.pillar === pillar).map((evaluation) => ({
        id: evaluation.id,
        cells: Object.fromEntries(columns.map((agent) => {
          const key = agentKey(agent);
          return [key, evalCell(evaluation, mode, groups.get(JSON.stringify([evaluation.id, mode, key])) ?? [])];
        })),
      }));
      table.pillars[pillar] = {
        evals,
        cells: Object.fromEntries(columns.map((agent) => {
          const key = agentKey(agent);
          return [key, pillarCell(evals.map((entry) => entry.cells[key]))];
        })),
      };
    }
    for (const agent of columns) {
      const key = agentKey(agent);
      const cells = pillars.map((pillar) => table.pillars[pillar].cells[key]);
      const epochs = pillars.flatMap((pillar) => table.pillars[pillar].evals.flatMap((entry) => entry.cells[key].epochs));
      const scored = epochs.filter((epoch) => epoch.status !== "error");
      const scores: ConfigurationSummary["scores"] = { overall: null, concepts: null, transactions: null, building: null, security: null };
      for (const pillar of pillars) scores[pillar] = table.pillars[pillar].cells[key].score;
      scores.overall = overallScore(pillars.map((pillar) => scores[pillar]));
      table.summaries[key] = {
        scores, costPerPass: costPerPass(epochs),
        medianTokens: median(scored.map((epoch) => epoch.total_tokens)),
        passed: cells.reduce((sum, cell) => sum + cell.passed, 0),
        total: cells.reduce((sum, cell) => sum + cell.total, 0),
        errors: cells.reduce((sum, cell) => sum + cell.errors, 0),
      };
    }
    tables[mode] = table;
  }
  const lifts: BoardData["lifts"] = {};
  for (const key of configurations.keys()) {
    const lift: ConfigurationSummary["scores"] = { overall: null, concepts: null, transactions: null, building: null, security: null };
    for (const pillar of pillars) {
      const internet = tables.internet.pillars[pillar].evals;
      const skills = tables.skills.pillars[pillar].evals;
      const paired = internet.map((entry, index) => skillLift(skills[index].cells[key].score, entry.cells[key].score));
      lift[pillar] = overallScore(paired);
    }
    lift.overall = overallScore(pillars.map((pillar) => lift[pillar]));
    lifts[key] = lift;
  }
  return {
    demo, tables, lifts, counts: { evals: evaluations.length, agents: configurations.size, runs: rows.length },
    evaluations: Object.fromEntries(evaluations.map((evaluation) => [evaluation.id, {
      id: evaluation.id, title: evaluation.title, pillar: evaluation.pillar,
      motivation: evaluation.motivation, prompt: evaluation.prompt, choices: evaluation.choices, modes: evaluation.modes,
    }])),
  };
}

export function epochCost(row: Pick<Row, "model_cost_usd" | "grader_cost_usd">): number | null {
  return row.model_cost_usd === null || row.grader_cost_usd === null
    ? null : row.model_cost_usd + row.grader_cost_usd;
}
