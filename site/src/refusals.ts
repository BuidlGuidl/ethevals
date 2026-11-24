import { agentKey, configurationSummary, overallScore, pillarCell, pillars, type BoardData, type EvalCell, type Pillar, type Table, type Trial } from "./board";
import { names } from "./labels";

type RefusalTrial = Pick<Trial, "score" | "no_answer">;

// A safety refusal on both tries ends the trial at 0% through the no_answer entry check.
export function isRefusedTrial({ score, no_answer }: RefusalTrial): boolean {
  return score.value !== null && score.stop?.kind === "entry" && score.stop.name === "no_answer"
    && no_answer?.at(-1)?.kind === "refused";
}

// Safety refusals a trial got past on the automatic retry. They leave its score alone.
export function retryRefusals(trial: RefusalTrial): number {
  return isRefusedTrial(trial) ? 0 : (trial.no_answer ?? []).filter((entry) => entry.kind === "refused").length;
}

export const refusedCount = (cells: Pick<EvalCell, "trials">[]) =>
  cells.reduce((sum, cell) => sum + cell.trials.filter(isRefusedTrial).length, 0);

export const tableHasRefusals = (table: Table) =>
  pillars.some((pillar) => table.pillars[pillar].evals.some((entry) => refusedCount(Object.values(entry.cells)) > 0));

// True for a table from ignoreRefusals that had refusals to leave out.
export const ignoresRefusals = (table: Table) =>
  pillars.some((pillar) => table.pillars[pillar].evals.some((entry) => Object.values(entry.cells).some((cell) => cell.trials.some((trial) => trial.ignored))));

function ignoreCell(cell: EvalCell): EvalCell {
  const refused = cell.trials.filter(isRefusedTrial);
  if (!refused.length) return cell;
  const trials = cell.trials.map((trial): Trial => isRefusedTrial(trial) ? { ...trial, ignored: true } : trial);
  const total = cell.total - refused.length;
  return {
    ...cell, trials, total,
    passed: cell.passed - refused.filter((trial) => trial.status === "passed").length,
    score: overallScore(trials.filter((trial) => !trial.ignored).map((trial) => trial.score.value)),
    state: cell.state === "score" && !total ? "pending" : cell.state,
  };
}

function ignoreTable(table: Table): Table {
  if (!tableHasRefusals(table)) return table;
  const rows = {} as Table["pillars"];
  for (const pillar of pillars) {
    const evals = table.pillars[pillar].evals.map((entry) => ({
      id: entry.id, cells: Object.fromEntries(Object.entries(entry.cells).map(([key, cell]) => [key, ignoreCell(cell)])),
    }));
    rows[pillar] = { evals, cells: Object.fromEntries(table.agents.map((agent) =>
      [agentKey(agent), pillarCell(evals.map((entry) => entry.cells[agentKey(agent)]))])) };
  }
  return { agents: table.agents, pillars: rows,
    summaries: Object.fromEntries(table.agents.map((agent) => [agentKey(agent), configurationSummary(rows, agentKey(agent))])) };
}

// The board with refused-twice trials left out of every average. Tasks left without a scored trial
// drop out of their pillar, the same way unrun tasks do. Refused trials stay listed, marked ignored.
export function ignoreRefusals(data: BoardData): BoardData {
  return { ...data, tables: { internet: ignoreTable(data.tables.internet), skills: ignoreTable(data.tables.skills),
    vanilla: ignoreTable(data.tables.vanilla) } };
}

export interface Refusals {
  refused: number;
  // Score with refused trials left out, and the tasks that still have a score, for each pillar with refusals.
  without: number | null;
  coverage: { pillar: Pillar; scored: number; tasks: number }[];
}

// `table` is a table from ignoreRefusals, so scores and coverage leave refused trials out.
export function refusals(table: Table, key: string, scope: Pillar | "overall"): Refusals {
  const coverage = pillars.filter((pillar) => scope === "overall" || scope === pillar).flatMap((pillar) => {
    const cells = table.pillars[pillar].evals.map((entry) => entry.cells[key]).filter((cell) => cell.state !== "na");
    const refused = refusedCount(cells);
    return refused ? [{ pillar, refused, scored: table.pillars[pillar].cells[key].scoredEvals, tasks: cells.length }] : [];
  });
  return {
    refused: coverage.reduce((sum, entry) => sum + entry.refused, 0),
    without: table.summaries[key].scores[scope],
    coverage: coverage.map(({ pillar, scored, tasks }) => ({ pillar, scored, tasks })),
  };
}

export const precise = (score: number | null) => score === null ? "–" : `${(score * 100).toFixed(1)}%`;
const trials = (count: number) => `${count} refused ${count === 1 ? "trial" : "trials"}`;
const coverageText = ({ coverage }: Refusals) =>
  coverage.map(({ pillar, scored, tasks }) => `${scored} of ${tasks} ${names[pillar]} tasks`).join(" and ");

// One sentence for a leaderboard or Compare score.
export function refusalText(info: Refusals, ignoring: boolean): string {
  return ignoring ? `${trials(info.refused)} ignored. ${coverageText(info)} scored.`
    : `${trials(info.refused)} scored as 0%. Without refusals: ${precise(info.without)}, with ${coverageText(info)} scored.`;
}

// One sentence for a task score.
export function taskRefusalText(cell: EvalCell, ignoring: boolean): string {
  const count = cell.trials.filter(isRefusedTrial).length;
  if (!ignoring) return `${trials(count)} scored as 0%.`;
  return `${trials(count)} ignored.${cell.score === null ? " No scored trials left." : ""}`;
}

export function refusalStrip(table: Table): string {
  const counts = table.agents.map((agent) => refusals(table, agentKey(agent), "overall").refused).filter(Boolean);
  const total = counts.reduce((sum, count) => sum + count, 0);
  return `Ignoring ${total} safety-refused ${total === 1 ? "trial" : "trials"} across ${counts.length} ${counts.length === 1 ? "agent" : "agents"}. Tasks left without a scored trial are left out of averages.`;
}
