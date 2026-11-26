"use client";
import { useState, type CSSProperties, type ReactNode } from "react";
import { AlertTriangle, Info, ShieldBan } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { sentences } from "../src/refusals";
import { pillarTaskCap } from "../src/board";
export const percent = (score: number | null) => score === null ? "–" : `${Math.round(score * 100)}%`;
// Every cost on the site: whole dollars from $10, cents from $1, two significant digits below.
const usd = (options: Intl.NumberFormatOptions) => new Intl.NumberFormat("en", { style: "currency", currency: "USD", ...options });
const dollars = usd({ maximumFractionDigits: 0 }), cents = usd({ minimumFractionDigits: 2 }),
  small = usd({ minimumFractionDigits: 2, maximumFractionDigits: 6 });
export const money = (value: number | null) => value === null ? "–" : value === 0 ? "$0"
  : value >= 9.995 ? dollars.format(value) : value >= 0.995 ? cents.format(value) : small.format(Number(value.toPrecision(2)));
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
// One sentence per line, so a tooltip never runs ideas together.
export const formulas = {
  overall: [`Each pillar counts by its number of tasks, up to ${pillarTaskCap}.`, "Pillars without a score are skipped."],
  pillar: ["Pillar scores average task scores.", "Tasks without a score are skipped."],
  lift: ["Lift = mean change over tasks scored in both modes for the same configuration, in percentage points.", `Overall weights pillar lifts by task count, up to ${pillarTaskCap}.`],
};
export const unscored = (count: number) => `${count} ${count === 1 ? "trial has" : "trials have"} no score yet.`;
// A string splits on newlines; each line shows on its own row.
type Lines = string | string[];
const toLines = (text: Lines) => typeof text === "string" ? text.split("\n") : text;
// Tooltip body: plain lines, then bullets set apart below a rule.
export function TipBody({ text, bullets }: { text?: Lines; bullets?: string[] }) {
  return <>{text !== undefined && <span className="tip-lines">{toLines(text).map((line, index) => <span key={index}>{line}</span>)}</span>}
    {bullets && bullets.length > 0 && <ul className="tip-bullets">{bullets.map((line) => <li key={line}>{line}</li>)}</ul>}</>;
}
export function Hint({ text, bullets, children }: { text?: Lines; bullets?: string[]; children: React.ReactElement }) {
  return <Tooltip disableHoverableContent><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent className="tip max-w-[min(90vw,480px)]"><TipBody text={text} bullets={bullets} /></TooltipContent></Tooltip>;
}

export function InfoHint({ label, text, align }: { label: string; text: Lines; align?: "start" | "center" | "end" }) {
  const [open, setOpen] = useState(false);
  return <Tooltip open={open} onOpenChange={setOpen} disableHoverableContent><TooltipTrigger asChild>
    <button type="button" className="info-hint" aria-label={`${label}: ${toLines(text).join(" ")}`}
      onClick={(event) => { event.preventDefault(); setOpen(true); }}><Info size={14} aria-hidden="true" /></button>
  </TooltipTrigger><TooltipContent align={align} className="tip max-w-[min(90vw,480px)]"><TipBody text={text} /></TooltipContent></Tooltip>;
}
// Sits in the corner of a score that still has planned trials without a score.
export function Unscored({ count }: { count: number }) {
  return <Hint text={unscored(count)}><span className="unscored-info" role="img" aria-label={unscored(count)}><AlertTriangle aria-hidden="true" /></span></Hint>;
}
// Marks a score that has trials ended by a safety refusal. Kept apart from the amber unscored icon.
export function RefusalMark({ lines, inline = false }: { lines: string[]; inline?: boolean }) {
  return <Hint bullets={lines}><span className={inline ? "refusal-info refusal-inline-mark" : "refusal-info"} role="img" aria-label={sentences(lines)} tabIndex={0}><ShieldBan aria-hidden="true" /></span></Hint>;
}
// Corner icons for one score. Both can show; they sit side by side.
export function CornerMarks({ missing = 0, refusal }: { missing?: number; refusal?: string[] }) {
  if (!missing && !refusal) return null;
  return <span className="corner-marks">{refusal && <RefusalMark lines={refusal} />}{missing > 0 && <Unscored count={missing} />}</span>;
}
export function Score({ score, lift, onOpen, label, peers, best, empty = "No trials yet", missing = 0, refusal, sub }: {
  score: number | null; lift?: number | null; onOpen: () => void; label: string;
  peers: Peers; best: string; empty?: string; missing?: number;
  // Refusal lines show on the shield icon tooltip; `sub` adds a line under the score.
  refusal?: string[]; sub?: ReactNode;
}) {
  const note = score !== null && missing > 0 ? unscored(missing) : "";
  const hasLift = lift !== undefined && lift !== null;
  const hint = score === null ? [empty] : [standing(score, peers, best), ...(hasLift ? formulas.lift : [])];
  return <div className="score-wrap"><Hint text={hint}>
    <button className="score-cell" {...tile(score, peers)} onClick={onOpen}
      aria-label={`${label}. ${score === null ? empty : percent(score)}.${note && ` ${note}`}${refusal ? ` ${sentences(refusal)}` : ""} Open details.`}>
      <span>{percent(score)}</span>{sub}{hasLift && <small className={lift < 0 ? "negative" : "lift"}>{pp(lift)}</small>}
    </button>
  </Hint><CornerMarks missing={note ? missing : 0} refusal={refusal} /></div>;
}
