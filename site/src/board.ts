import type { Row } from "./rows";
import { taskDomain, type Domain } from "./areas";
import { checkPoints, defaultScoring, trialScore, type Scoring } from "./scoring";
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

export type Trial = Pick<Row, "trial" | "status" | "checks" | "error_kind" | "error_reason"
  | "total_tokens" | "total_seconds" | "model_cost_usd" | "judge_cost_usd"
  | "cost_source" | "limit" | "paid_by" | "no_answer"> & {
  cost: number | null;
  issue: string;
  trajectoryUrl: string | null;
  // Set only when a version other than all or nothing is selected.
  score?: number;
  points?: Record<string, number>;
};

interface Counts {
  score: number | null;
  passed: number;
  total: number;
  errors: number;
}
export interface EvalCell extends Counts {
  state: "score" | "na" | "pending";
  trials: Trial[];
  // A multi-check task under a version other than all or nothing shows its score, not passed/total.
  percent?: true;
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
  scoring: Scoring;
  evaluations: Record<string, DisplayEval>;
  tables: Record<Mode, Table>;
  lifts: Record<string, Record<Pillar | "overall", number | null>>;
  counts: { evals: number; agents: number; runs: number };
}

export function overallScore(scores: (number | null)[]): number | null {
  const scored = scores.filter((score): score is number => score !== null);
  return scored.length ? scored.reduce((sum, score) => sum + score, 0) / scored.length : null;
}

export function scoreSummary(cells: Counts[]): Counts {
  return {
    score: overallScore(cells.map((cell) => cell.score)),
    passed: cells.reduce((sum, cell) => sum + cell.passed, 0),
    total: cells.reduce((sum, cell) => sum + cell.total, 0),
    errors: cells.reduce((sum, cell) => sum + cell.errors, 0),
  };
}

export function emptyTrialLabel(cell: EvalCell): string {
  return cell.state === "na" ? "Not applicable" : cell.errors ? `${cell.errors} errors; no scored trials` : "No trials yet";
}

export function costPerPass(trials: Pick<Trial, "status" | "model_cost_usd">[]): number | null {
  const scored = trials.filter((trial) => trial.status !== "error");
  const passed = scored.filter((trial) => trial.status === "passed").length;
  if (!passed || scored.some((trial) => trial.model_cost_usd === null)) return null;
  return scored.reduce((sum, trial) => sum + trial.model_cost_usd!, 0) / passed;
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

function evalCell(evaluation: Eval, mode: Mode, rows: Row[]): EvalCell {
  const scored = rows.filter((row) => row.status !== "error");
  const passed = scored.filter((row) => row.status === "passed").length;
  return {
    state: !evaluation.modes.includes(mode) ? "na" : scored.length ? "score" : "pending",
    score: scored.length ? passed / scored.length : null,
    passed, total: scored.length, errors: rows.length - scored.length,
    trials: rows.sort((a, b) => a.trial - b.trial).map((row) => ({
      trial: row.trial, status: row.status, checks: row.checks, error_kind: row.error_kind,
      error_reason: row.error_reason, total_tokens: row.total_tokens, total_seconds: row.total_seconds,
      model_cost_usd: row.model_cost_usd, judge_cost_usd: row.judge_cost_usd,
      cost_source: row.cost_source,
      paid_by: row.paid_by,
      no_answer: row.no_answer,
      limit: row.limit,
      cost: trialCost(row), issue: row.error_reason ?? (row.limit
        ? [...new Set(Object.values(row.checks).filter((check) => !check.passed).map((check) => check.reason))].join(" ")
        : ""),
      trajectoryUrl: row.trajectory_url,
    })),
  };
}

function pillarCell(cells: EvalCell[]): PillarCell {
  const scored = cells.filter((cell) => cell.score !== null);
  return {
    state: !cells.some((cell) => cell.state !== "na") ? "empty" : scored.length ? "score" : "pending",
    ...scoreSummary(cells),
    scoredEvals: scored.length,
  };
}

// Pillar cells and summaries follow from the task cells, so a new trial score only needs this again.
function summarize(table: Table): Table {
  const summaries: Table["summaries"] = {};
  const scored = { ...table, pillars: Object.fromEntries(pillars.map((pillar) => {
    const { evals } = table.pillars[pillar];
    return [pillar, { evals, cells: Object.fromEntries(table.agents.map((agent) => {
      const key = agentKey(agent);
      return [key, pillarCell(evals.map((entry) => entry.cells[key]))];
    })) }];
  })) as Table["pillars"], summaries };
  for (const agent of table.agents) {
    const key = agentKey(agent);
    const cells = pillars.map((pillar) => scored.pillars[pillar].cells[key]);
    const summary = scoreSummary(cells);
    const trials = pillars.flatMap((pillar) => scored.pillars[pillar].evals.flatMap((entry) => entry.cells[key].trials));
    const counted = trials.filter((trial) => trial.status !== "error");
    const scores: ConfigurationSummary["scores"] = { overall: null, concepts: null, build: null, act: null };
    for (const pillar of pillars) scores[pillar] = scored.pillars[pillar].cells[key].score;
    scores.overall = summary.score;
    summaries[key] = {
      scores, costPerPass: costPerPass(trials),
      medianTokens: median(counted.map((trial) => trial.total_tokens)),
      passed: summary.passed, total: summary.total, errors: summary.errors,
    };
  }
  return scored;
}

function lifts(tables: BoardData["tables"], keys: string[]): BoardData["lifts"] {
  return Object.fromEntries(keys.map((key) => {
    const lift: ConfigurationSummary["scores"] = { overall: null, concepts: null, build: null, act: null };
    for (const pillar of pillars) {
      const internet = tables.internet.pillars[pillar].evals;
      const skills = tables.skills.pillars[pillar].evals;
      const paired = internet.map((entry, index) => skillLift(skills[index].cells[key].score, entry.cells[key].score));
      lift[pillar] = overallScore(paired);
    }
    lift.overall = overallScore(pillars.map((pillar) => lift[pillar]));
    return [key, lift];
  }));
}

// Scores a board built under all or nothing with another version. A task's score is the mean of its trial scores.
export function scoreBoard(data: BoardData, scoring: Scoring): BoardData {
  if (scoring === data.scoring) return data;
  const rescore = (id: string, cells: Record<string, EvalCell>) => {
    const percent = Object.values(cells).some((cell) => cell.trials.some((trial) => Object.keys(trial.checks).length > 1));
    return Object.fromEntries(Object.entries(cells).map(([key, cell]) => {
      const trials = cell.trials.map((trial) => ({ ...trial, score: trialScore(id, trial, scoring),
        ...(scoring === "weighted" && { points: checkPoints(id, Object.keys(trial.checks), scoring)! }) }));
      const scores = trials.filter((trial) => trial.status !== "error").map((trial) => trial.score);
      return [key, { ...cell, trials, score: overallScore(scores), ...(percent && { percent: true as const }) }];
    }));
  };
  const tables = Object.fromEntries(Object.entries(data.tables).map(([mode, table]) => [mode, summarize({ ...table,
    pillars: Object.fromEntries(pillars.map((pillar) => [pillar, { cells: {},
      evals: table.pillars[pillar].evals.map(({ id, cells }) => ({ id, cells: rescore(id, cells) })) }])) as Table["pillars"] })])) as BoardData["tables"];
  return { ...data, scoring, tables, lifts: lifts(tables, Object.keys(data.lifts)) };
}

// The loader supplies current, checked rows. Group each row and compute each cell once.
export function buildBoard(evaluations: Eval[], rows: Row[], demo = false): BoardData {
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
          return [key, evalCell(evaluation, mode, groups.get(JSON.stringify([evaluation.id, mode, key])) ?? [])];
        })),
      }));
      table.pillars[pillar] = { evals, cells: {} };
    }
    tables[mode] = summarize(table);
  }
  return {
    demo, scoring: defaultScoring, tables, lifts: lifts(tables, [...configurations.keys()]), counts: { evals: evaluations.length, agents: configurations.size, runs: rows.length },
    evaluations: Object.fromEntries(evaluations.map((evaluation) => [evaluation.id, {
      id: evaluation.id, title: evaluation.title, pillar: evaluation.pillar, domain: taskDomain(evaluation),
      description: evaluation.description, instruction: evaluation.instruction, modes: evaluation.modes,
    }])),
  };
}

export function trialCost(row: Pick<Row, "model_cost_usd" | "judge_cost_usd">): number | null {
  return row.model_cost_usd === null || row.judge_cost_usd === null
    ? null : row.model_cost_usd + row.judge_cost_usd;
}
