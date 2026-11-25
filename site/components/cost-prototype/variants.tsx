"use client";

// THROWAWAY PROTOTYPE. Three ways to show what each board row spent, picked with ?variant=a|b|c.
// ?variant=none renders the board without cost. Fold the winner into app/board.tsx and delete this folder.

import { useEffect, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { names } from "../../src/labels";
import { pillars, type Pillar } from "../../src/board";
import { Hint } from "../scores";
import { updateQuery } from "../url-state";
import { dollars, payer, scopeCost, type RowCost } from "./cost";

export const variants = { a: "Total", b: "Price signs", c: "Per task" } as const;
export type Variant = keyof typeof variants | "none";
const order = Object.keys(variants) as (keyof typeof variants)[];
export const readVariant = (value: string | null): Variant => value === "none" ? "none" : order.find((variant) => variant === value) ?? "a";

const noop = () => () => {};
export function VariantPicker({ variant }: { variant: Variant }) {
  // Client only: the URL holds the variant, and the server page stays free of prototype markup.
  const client = useSyncExternalStore(noop, () => true, () => false);
  const step = (by: number) => updateQuery({ variant: order[(order.indexOf(variant as keyof typeof variants) + by + order.length) % order.length] });
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.metaKey || event.ctrlKey || event.altKey || target?.closest("input, textarea, select, [contenteditable]")) return;
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === "ArrowRight") step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  if (variant === "none" || !client) return null;
  return <div className="variant-picker" role="group" aria-label="Prototype variant">
    <button type="button" onClick={() => step(-1)} aria-label="Previous variant"><ChevronLeft size={14} /></button>
    <span aria-live="polite">Variant {variant.toUpperCase()} · {variants[variant]}</span>
    <button type="button" onClick={() => step(1)} aria-label="Next variant"><ChevronRight size={14} /></button>
  </div>;
}

const perTask = (total: number, tasks: number) => tasks ? total / tasks : 0;

function Tip({ text, children }: { text: string[]; children: ReactNode }) {
  return <Hint text={text}><span className="row-cost" tabIndex={0}>{children}</span></Hint>;
}

// Price signs: one to four, scaled against the dearest row in the same table.
function Signs({ total, max }: { total: number; max: number }) {
  const filled = max > 0 ? Math.min(4, Math.max(1, Math.ceil(4 * total / max))) : 1;
  return <span className="price-signs" aria-label={`${filled} of 4`}>
    <span>{"$".repeat(filled)}</span><span aria-hidden="true">{"$".repeat(4 - filled)}</span></span>;
}

// The cost after "harness · effort" on a leaderboard row label.
export function LabelCost({ variant, cost, max }: { variant: Variant; cost: RowCost; max: number }): ReactNode {
  if (variant === "a") return <Tip text={[payer(cost)]}>{dollars(cost.total)}</Tip>;
  if (variant === "b") return <Tip text={[`${dollars(cost.total)} · ${payer(cost)}`]}><Signs total={cost.total} max={max} /></Tip>;
  if (variant === "c") return <Tip text={[`${dollars(cost.total)} over ${cost.tasks} tasks · ${payer(cost)}`]}>{dollars(perTask(cost.total, cost.tasks))} a task</Tip>;
  return null;
}

// Variant A: the cost joins "N scored trials" in the drawer header.
export function HeaderCost({ variant, cost, pillar }: { variant: Variant; cost: RowCost; pillar?: Pillar }): ReactNode {
  if (variant !== "a") return null;
  return <> · <Tip text={[payer(cost)]}>{dollars(scopeCost(cost, pillar).total)}</Tip></>;
}

// Variants B and C: a block under the drawer score.
export function DrawerCost({ variant, cost, pillar }: { variant: Variant; cost: RowCost; pillar?: Pillar }): ReactNode {
  const scope = scopeCost(cost, pillar);
  if (variant === "b") {
    const boxes: [string, number][] = [["Total", scope.total], ["Agent", scope.agent], ["Judge", scope.judge],
      ...(pillar ? [] : pillars.map((value): [string, number] => [names[value], cost.pillars[value].total]))];
    return <div className="cost-boxes" role="group" aria-label="Cost">
      {boxes.map(([label, value]) => <div key={label}><span>{label}</span><b>{dollars(value)}</b>
        {label === "Total" && <small>{payer(cost)}</small>}</div>)}
    </div>;
  }
  if (variant === "c") return <p className="drawer-cost"><Tip text={[payer(cost)]}>{dollars(scope.total)}</Tip> total · {dollars(perTask(scope.total, scope.tasks))} a task</p>;
  return null;
}

// What a task row in the drawer list shows for its cost. `max` is the dearest task in the drawer.
export function TaskCost({ variant, value, max }: { variant: Variant; value: number | undefined; max: number }): ReactNode {
  if (value === undefined) return null;
  if (variant === "a") return <span className="task-cost">{dollars(value)}</span>;
  if (variant === "c") return <span className="task-cost-bar">
    <span className="cost-track" aria-hidden="true"><span style={{ "--share": `${max > 0 ? value / max * 100 : 0}%` } as CSSProperties} /></span>
    <span className="task-cost">{dollars(value)}</span></span>;
  return null;
}

// The dearest task a drawer lists, for variant C's bars.
export function dearestTask(cost: RowCost, ids: string[]): number {
  return Math.max(0, ...ids.map((id) => cost.byTask[id] ?? 0));
}
