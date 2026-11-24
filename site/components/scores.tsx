"use client";
import { useState, type CSSProperties } from "react";
import { Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
export const percent = (score: number | null) => score === null ? "–" : `${Math.round(score * 100)}%`;
export const money = (value: number | null, digits = 2) => value === null ? "–" : `$${value.toFixed(digits)}`;
export const pp = (value: number | null) => value === null ? "–" : `${Math.round(value) > 0 ? "+" : ""}${Math.round(value)}pp`;
// Tile color and tooltip compare a score with the best score among its peers: a leaderboard column or a task row.
// Both use rounded percentages, so two tiles showing the same number look the same.
export type Peers = { top: number | null; tied: boolean };
const whole = (score: number) => Math.round(score * 100);
export function peers(scores: (number | null)[]): Peers {
  const rounded = scores.filter((score) => score !== null).map(whole);
  const top = rounded.length ? Math.max(...rounded) : null;
  return { top, tied: top !== null && rounded.filter((value) => value === top).length > 1 };
}
export type Tone = "leader" | "trail" | "far" | "zero";
export function tile(score: number | null, { top }: Peers): { "data-empty": boolean; "data-tone"?: Tone; style?: CSSProperties } {
  if (score === null || top === null) return { "data-empty": true };
  const value = whole(score), gap = top - value;
  if (value === 0) return { "data-empty": false, "data-tone": "zero" };
  if (gap === 0) return { "data-empty": false, "data-tone": "leader" };
  const fade = 1 - Math.exp(-gap / 28);
  return { "data-empty": false, "data-tone": gap > 50 ? "far" : "trail", style: { "--heat": `${((1 - fade) * 100).toFixed(1)}%` } as CSSProperties };
}
export function standing(score: number, { top, tied }: Peers, best: string): string {
  if (!top) return "No model scored";
  const gap = top - whole(score);
  if (gap === 0) return tied ? "Tied for best" : best;
  return `\u2212${gap} ${gap === 1 ? "pt" : "pts"} · best ${top}%`;
}
export const formulas = {
  overall: "Overall averages pillar scores. Pillars without a score are skipped.",
  pillar: "Pillar score averages task scores. Tasks without a score are skipped.",
  lift: "Lift = mean change over tasks scored in both modes for the same configuration, in percentage points. Overall averages paired pillar lifts.",
};
export const unscored = (count: number) => `${count} ${count === 1 ? "trial has" : "trials have"} no score yet.`;
export function Hint({ text, children }: { text: string; children: React.ReactElement }) {
  return <Tooltip disableHoverableContent><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent className="whitespace-pre-line [overflow-wrap:anywhere]">{text}</TooltipContent></Tooltip>;
}

export function InfoHint({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false);
  return <Tooltip open={open} onOpenChange={setOpen} disableHoverableContent><TooltipTrigger asChild>
    <button type="button" className="info-hint" aria-label={`${label}: ${text}`}
      onClick={(event) => { event.preventDefault(); setOpen(true); }}><Info size={14} aria-hidden="true" /></button>
  </TooltipTrigger><TooltipContent className="max-w-80">{text}</TooltipContent></Tooltip>;
}
// Sits in the corner of a score that still has planned trials without a score.
export function Unscored({ count }: { count: number }) {
  return <Hint text={unscored(count)}><span className="unscored-info" role="img" aria-label={unscored(count)}><Info aria-hidden="true" /></span></Hint>;
}
export function Score({ score, lift, onOpen, label, peers, best, empty = "No trials yet", missing = 0 }: {
  score: number | null; lift?: number | null; onOpen: () => void; label: string;
  peers: Peers; best: string; empty?: string; missing?: number;
}) {
  const note = score !== null && missing > 0 ? unscored(missing) : "";
  const hint = score === null ? empty : `${standing(score, peers, best)}${lift !== undefined && lift !== null ? `\n${formulas.lift}` : ""}`;
  return <div className="score-wrap"><Hint text={hint}>
    <button className="score-cell" {...tile(score, peers)} onClick={onOpen}
      aria-label={`${label}. ${score === null ? empty : percent(score)}.${note && ` ${note}`} Open details.`}>
      <span>{percent(score)}</span>{lift !== undefined && lift !== null && <small className={lift < 0 ? "negative" : "lift"}>{pp(lift)}</small>}
    </button>
  </Hint>{note && <Unscored count={missing} />}</div>;
}
