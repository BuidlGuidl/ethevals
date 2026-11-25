// THROWAWAY PROTOTYPE. Row cost for the board, shown three ways with ?variant=a|b|c.
// Fold the winner into app/board.tsx and delete this folder.

import { pillars, type Pillar, type Table, type Trial } from "../../src/board";

export type Spend = { total: number; agent: number; judge: number };
export type RowCost = Spend & {
  // Some trial in the row ran on a plan, so the number is what the API would have charged.
  plan: boolean;
  trials: number;
  tasks: number;
  pillars: Record<Pillar, Spend & { tasks: number }>;
  // Task id to that task's spend, over its trials in this row.
  byTask: Record<string, number>;
};

// Agent and judge parts add separately: a trial missing one part still counts the other.
// Every trial counts, errors and refusals included, since each one spent money.
function spend(trials: Trial[]): Spend {
  const agent = trials.reduce((sum, trial) => sum + (trial.model_cost_usd ?? 0), 0);
  const judge = trials.reduce((sum, trial) => sum + (trial.judge_cost_usd ?? 0), 0);
  return { total: agent + judge, agent, judge };
}

export function rowCost(table: Table, key: string): RowCost {
  const byTask: Record<string, number> = {};
  const perPillar = {} as RowCost["pillars"];
  const all: Trial[] = [];
  for (const pillar of pillars) {
    const trials: Trial[] = [];
    let tasks = 0;
    for (const entry of table.pillars[pillar].evals) {
      const cell = entry.cells[key];
      if (!cell?.trials.length) continue;
      tasks += 1;
      byTask[entry.id] = spend(cell.trials).total;
      trials.push(...cell.trials);
    }
    perPillar[pillar] = { ...spend(trials), tasks };
    all.push(...trials);
  }
  return {
    ...spend(all), plan: all.some((trial) => trial.paid_by === "plan"), trials: all.length,
    tasks: pillars.reduce((sum, pillar) => sum + perPillar[pillar].tasks, 0), pillars: perPillar, byTask,
  };
}

// The drawer's scope: one pillar, or all of them for Overall.
export function scopeCost(cost: RowCost, pillar?: Pillar): Spend & { tasks: number } {
  return pillar ? cost.pillars[pillar] : { total: cost.total, agent: cost.agent, judge: cost.judge, tasks: cost.tasks };
}

// Under $10 shows cents; $10 and up shows whole dollars.
export const dollars = (value: number) => value < 10 ? `$${value.toFixed(2)}` : `$${Math.round(value).toLocaleString("en")}`;
export const payer = (cost: RowCost) => cost.plan ? "At API prices, paid by plan" : "Paid with an API key";
