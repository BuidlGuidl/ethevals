"use client";

// THROWAWAY PROTOTYPE. Three ways to show safety refusals on the leaderboard, picked with ?variant=a|b|c.
// Fold the winner into app/board.tsx and delete this folder.

import { useEffect, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, ShieldBan } from "lucide-react";
import type { Refusals } from "../../src/refusals";
import { percent } from "../scores";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { setIgnoringRefusals, updateQuery } from "../url-state";

export const variants = { a: "Quiet icon", b: "Inline count", c: "Counterfactual delta" } as const;
export type Variant = keyof typeof variants;
const order = Object.keys(variants) as Variant[];
export const readVariant = (value: string | null): Variant => order.find((variant) => variant === value) ?? "a";

export function VariantPicker({ variant }: { variant: Variant }) {
  const step = (by: number) => updateQuery({ variant: order[(order.indexOf(variant) + by + order.length) % order.length] });
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
  return <div className="variant-picker" role="group" aria-label="Prototype variant">
    <button type="button" onClick={() => step(-1)} aria-label="Previous variant"><ChevronLeft size={14} /></button>
    <span aria-live="polite">Variant {variant.toUpperCase()} · {variants[variant]}</span>
    <button type="button" onClick={() => step(1)} aria-label="Next variant"><ChevronRight size={14} /></button>
  </div>;
}

// A compact switch. Variants A and C and the Compare page use it.
export function RefusalSwitch({ ignoring }: { ignoring: boolean }) {
  return <button type="button" role="switch" aria-checked={ignoring} className="refusal-switch" onClick={() => setIgnoringRefusals(!ignoring)}>
    <span className="refusal-switch-track" aria-hidden="true"><span /></span>Ignore refusals
  </button>;
}

export function RefusalToggle({ variant, ignoring }: { variant: Variant; ignoring: boolean }) {
  if (variant !== "b") return <RefusalSwitch ignoring={ignoring} />;
  return <div className="mode-toggle refusal-segment" role="group" aria-label="Refusals">
    <span className="refusal-segment-label">Refusals</span>
    <ToggleGroup type="single" value={ignoring ? "ignore" : "count"} onValueChange={(value) => value && setIgnoringRefusals(value === "ignore")}
      className="border-0 [&>*+*]:-ml-px" aria-label="How refused trials count">
      <ToggleGroupItem value="count" className="border border-border-strong">Count as 0%</ToggleGroupItem>
      <ToggleGroupItem value="ignore" className="border border-border-strong">Ignore</ToggleGroupItem>
    </ToggleGroup>
  </div>;
}

// What a leaderboard score adds for its refusals in each variant.
export function scoreExtras(variant: Variant, info: Refusals, ignoring: boolean, baseline: number | null, overall: boolean): { mark: boolean; sub?: ReactNode } {
  if (variant === "b") return { mark: false, sub: <span className="score-sub refusal-sub">
    <ShieldBan aria-hidden="true" />{ignoring ? `${info.refused} ignored` : `${info.refused} refused`}</span> };
  if (variant === "c" && ignoring) {
    // Overall spans pillars, so a bare task count there would not say which pillar it counts.
    const coverage = !overall && info.coverage.length === 1 ? ` · ${info.coverage[0].scored}/${info.coverage[0].tasks}` : "";
    return { mark: true, sub: <span className="score-sub">was {percent(baseline)}{coverage}</span> };
  }
  return { mark: true };
}

export function RefusalStrip({ text }: { text: string }) {
  return <p className="refusal-strip"><ShieldBan aria-hidden="true" />{text}</p>;
}
