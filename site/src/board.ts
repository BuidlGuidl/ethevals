import type { Row } from "./rows";
import { taskDomain, type Domain } from "./areas";
import { scoreTrial, type CheckTags, type TrialScore } from "./scoring";
export type { Row } from "./rows";

export const pillars = ["concepts", "build", "act"] as const;
export type Pillar = (typeof pillars)[number];
export type Mode = "vanilla" | "internet" | "skills";
export const layers = ["contracts", "frontend", "backend"] as const;
export type Layer = (typeof layers)[number];

export interface Eval {
  id: string;
  hash: string;
  instruction_hash: string;
  environment_hash: string;
  checks_hash: string;
  checks?: CheckTags;
  title: string;
  pillar: Pillar;
  area?: string | null;
  layer?: Layer | null;
  description: string;
  instruction: string;
  modes: Mode[];
}
export type DisplayEval = Omit<Eval, "hash" | "instruction_hash" | "environment_hash" | "checks_hash"> & { domain: Domain };

export interface Agent {
  model: string;
  agent: string | null;
  effort: string | null;
}

export type Trial = Pick<Row, "trial" | "status" | "checks" | "error_kind"
  | "total_tokens" | "total_seconds" | "cost_source" | "limit" | "paid_by" | "no_answer"> & {
  // What the agent spent at API prices. The judge's cost is left out.
  cost: number | null;
  score: TrialScore;
  // Set on a refused trial while the board ignores refusals. It stays listed but leaves the averages.
  ignored?: true;
  issue: string;
  trajectoryUrl: string | null;
};

interface Counts {
  score: number | null;
  passed: number;
  total: number;
  errors: number;
  // Planned trials without a score: errors and trials not run yet.
  missing: number;
  // What the trials cost, errors and refusals included. Null when no trial has a price.
  cost: number | null;
}
export interface EvalCell extends Counts {
  state: "score" | "na" | "pending";
  trials: Trial[];
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
  medianTokens: number | null;
  passed: number;
  total: number;
  errors: number;
  missing: number;
  cost: number | null;
  // Some trial ran on a plan, so its cost is what the API would have charged.
  plan: boolean;
}
export interface BoardData {
  demo: boolean;
  evaluations: Record<string, DisplayEval>;
  tables: Record<Mode, Table>;
  lifts: Record<string, Record<Pillar | "overall", number | null>>;
  counts: { evals: number; agents: number; runs: number };
}

export function meanScore(scores: (number | null)[]): number | null {
  const scored = scores.filter((score): score is number => score !== null);
  return scored.length ? scored.reduce((sum, score) => sum + score, 0) / scored.length : null;
}

// Each pillar counts by its number of tasks, up to this cap (ADR 0035). At 25 tasks per pillar it is the plain average.
export const pillarTaskCap = 25;

// Overall from pillar scores. `tasks` counts the pillar's tasks in the view, the same for every configuration.
// Pillars without a score are skipped.
export function weightedOverall(parts: { score: number | null; tasks: number }[]): number | null {
  const scored = parts.filter((part): part is { score: number; tasks: number } => part.score !== null);
  const weight = scored.reduce((sum, part) => sum + Math.min(part.tasks, pillarTaskCap), 0);
  return weight ? scored.reduce((sum, part) => sum + Math.min(part.tasks, pillarTaskCap) * part.score, 0) / weight : null;
}

// Tasks in a pillar row that apply to the table's mode.
export const pillarTasks = (row: PillarRow, key: string) => row.evals.filter((entry) => entry.cells[key].state !== "na").length;

export function scoreSummary(cells: Counts[]): Counts {
  return {
    score: meanScore(cells.map((cell) => cell.score)),
    passed: cells.reduce((sum, cell) => sum + cell.passed, 0),
    total: cells.reduce((sum, cell) => sum + cell.total, 0),
    errors: cells.reduce((sum, cell) => sum + cell.errors, 0),
    missing: cells.reduce((sum, cell) => sum + cell.missing, 0),
    cost: totalCost(cells.map((cell) => cell.cost)),
  };
}

// Adds known costs. Null only when none is known.
export function totalCost(costs: (number | null)[]): number | null {
  const known = costs.filter((cost): cost is number => cost !== null);
  return known.length ? known.reduce((sum, cost) => sum + cost, 0) : null;
}

export function emptyTrialLabel(cell: EvalCell): string {
  return cell.state === "na" ? "Not applicable" : cell.errors ? `${cell.errors} ${cell.errors === 1 ? "error" : "errors"}. No scored trials.` : "No trials yet";
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
  return JSON.stringify([agent.model, agent.agent, agent.effort]);
}

function evalCell(evaluation: Eval, mode: Mode, rows: Row[], attempts: number): EvalCell {
  const scored = rows.filter((row) => row.status !== "error");
  const passed = scored.filter((row) => row.status === "passed").length;
  const trials = rows.sort((a, b) => a.trial - b.trial).map((row): Trial => {
    const score = scoreTrial(evaluation, row);
    const errored = score.value === null;
    return {
      trial: row.trial, status: row.status, score,
      checks: errored ? {} : row.checks, error_kind: errored ? null : row.error_kind,
      total_tokens: row.total_tokens, total_seconds: row.total_seconds,
      cost_source: row.cost_source,
      paid_by: row.paid_by,
      no_answer: errored ? undefined : row.no_answer,
      limit: errored ? null : row.limit,
      cost: row.model_cost_usd, issue: errored ? "" : (row.error_reason ?? (row.limit
        ? [...new Set(Object.values(row.checks).filter((check) => !check.passed).map((check) => check.reason))].join(" ")
        : "")),
      trajectoryUrl: row.trajectory_url,
    };
  });
  return {
    state: !evaluation.modes.includes(mode) ? "na" : scored.length ? "score" : "pending",
    score: meanScore(trials.map((trial) => trial.score.value)),
    passed, total: scored.length, errors: rows.length - scored.length,
    missing: evaluation.modes.includes(mode) ? Math.max(0, attempts - scored.length) : 0,
    cost: totalCost(trials.map((trial) => trial.cost)),
    trials,
  };
}

export function pillarCell(cells: EvalCell[]): PillarCell {
  const scored = cells.filter((cell) => cell.score !== null);
  return {
    state: !cells.some((cell) => cell.state !== "na") ? "empty" : scored.length ? "score" : "pending",
    ...scoreSummary(cells),
    scoredEvals: scored.length,
  };
}

export function configurationSummary(rows: Table["pillars"], key: string): ConfigurationSummary {
  const summary = scoreSummary(pillars.map((pillar) => rows[pillar].cells[key]));
  const trials = pillars.flatMap((pillar) => rows[pillar].evals.flatMap((entry) => entry.cells[key].trials));
  const scored = trials.filter((trial) => trial.status !== "error");
  const overall = weightedOverall(pillars.map((pillar) => ({ score: rows[pillar].cells[key].score, tasks: pillarTasks(rows[pillar], key) })));
  const scores: ConfigurationSummary["scores"] = { overall, concepts: null, build: null, act: null };
  for (const pillar of pillars) scores[pillar] = rows[pillar].cells[key].score;
  return {
    scores, medianTokens: median(scored.map((trial) => trial.total_tokens)),
    passed: summary.passed, total: summary.total, errors: summary.errors, missing: summary.missing,
    cost: summary.cost, plan: trials.some((trial) => trial.paid_by === "plan"),
  };
}

// The loader supplies current, checked rows. Group each row and compute each cell once.
// `attempts` is the job's planned trials per task. Zero leaves planned trials uncounted.
export function buildBoard(evaluations: Eval[], rows: Row[], demo = false, attempts = 0): BoardData {
  const groups = new Map<string, Row[]>();
  const agents: Record<Mode, Map<string, Agent>> = { internet: new Map(), skills: new Map(), vanilla: new Map() };
  for (const row of rows) {
    const key = agentKey(row);
    agents[row.mode].set(key, { model: row.model, agent: row.agent, effort: row.effort });
    const group = JSON.stringify([row.task_id, row.mode, key]);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)!.push(row);
  }
  const tables = {} as BoardData["tables"];
  const configurations = new Map([...agents.internet, ...agents.skills]);
  for (const mode of ["internet", "skills", "vanilla"] as const) {
    const columns = [...(mode === "vanilla" ? agents.vanilla : configurations).values()]
      .sort((a, b) => agentKey(a).localeCompare(agentKey(b), "en"));
    const table: Table = { agents: columns, pillars: {} as Table["pillars"], summaries: {} };
    // The knowledge table shows declared vanilla tasks. Both table and panel use these rows.
    const eligible = evaluations.filter((evaluation) => mode !== "vanilla" || evaluation.modes.includes("vanilla"));
    for (const pillar of pillars) {
      const evals = eligible.filter((evaluation) => evaluation.pillar === pillar).map((evaluation) => ({
        id: evaluation.id,
        cells: Object.fromEntries(columns.map((agent) => {
          const key = agentKey(agent);
          return [key, evalCell(evaluation, mode, groups.get(JSON.stringify([evaluation.id, mode, key])) ?? [], attempts)];
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
    for (const agent of columns) table.summaries[agentKey(agent)] = configurationSummary(table.pillars, agentKey(agent));
    tables[mode] = table;
  }
  const lifts: BoardData["lifts"] = {};
  for (const key of configurations.keys()) {
    const lift: ConfigurationSummary["scores"] = { overall: null, concepts: null, build: null, act: null };
    for (const pillar of pillars) {
      const internet = tables.internet.pillars[pillar].evals;
      const skills = tables.skills.pillars[pillar].evals;
      const paired = internet.map((entry, index) => skillLift(skills[index].cells[key].score, entry.cells[key].score));
      lift[pillar] = meanScore(paired);
    }
    lift.overall = weightedOverall(pillars.map((pillar) => ({ score: lift[pillar], tasks: pillarTasks(tables.internet.pillars[pillar], key) })));
    lifts[key] = lift;
  }
  return {
    demo, tables, lifts, counts: { evals: evaluations.length, agents: configurations.size, runs: rows.length },
    evaluations: Object.fromEntries(evaluations.map((evaluation) => [evaluation.id, {
      id: evaluation.id, title: evaluation.title, pillar: evaluation.pillar, domain: taskDomain(evaluation),
      description: evaluation.description, instruction: evaluation.instruction, modes: evaluation.modes,
      ...(evaluation.checks && { checks: evaluation.checks }),
    }])),
  };
}
