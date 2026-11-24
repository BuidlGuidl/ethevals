"use client";
import { useState, type CSSProperties, type ReactNode } from "react";
import { Info, ShieldBan } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
export const percent = (score: number | null) => score === null ? "–" : `${Math.round(score * 100)}%`;
export const money = (value: number | null, digits = 2) => value === null ? "–" : `$${value.toFixed(digits)}`;
export const pp = (value: number | null) => value === null ? "–" : `${Math.round(value) > 0 ? "+" : ""}${Math.round(value)}pp`;
export const heat = (score: number | null) => score === null ? undefined : { "--score": `${score * 100}%` } as CSSProperties;
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
// Marks a score that has trials ended by a safety refusal. Kept apart from the amber unscored icon.
export function RefusalMark({ text, inline = false }: { text: string; inline?: boolean }) {
  return <Hint text={text}><span className={inline ? "refusal-info refusal-inline-mark" : "refusal-info"} role="img" aria-label={text} tabIndex={0}><ShieldBan aria-hidden="true" /></span></Hint>;
}
// Corner icons for one score. Both can show; they sit side by side.
export function CornerMarks({ missing = 0, refusal }: { missing?: number; refusal?: string }) {
  if (!missing && !refusal) return null;
  return <span className="corner-marks">{refusal && <RefusalMark text={refusal} />}{missing > 0 && <Unscored count={missing} />}</span>;
}
export function Score({ score, lift, onOpen, label, formula, empty = "No trials yet", missing = 0, refusal, mark = true, sub }: {
  score: number | null; lift?: number | null; onOpen: () => void; label: string;
  formula: string; empty?: string; missing?: number;
  // Refusal sentence for the tooltip; `mark` shows the corner icon, `sub` adds a line under the score.
  refusal?: string; mark?: boolean; sub?: ReactNode;
}) {
  const note = score !== null && missing > 0 ? unscored(missing) : "";
  return <div className="score-wrap"><Hint text={[formula, lift !== undefined && lift !== null && formulas.lift, refusal].filter(Boolean).join("\n")}>
    <button className="score-cell" data-empty={score === null} style={heat(score)} onClick={onOpen}
      aria-label={`${label}. ${score === null ? empty : percent(score)}.${note && ` ${note}`}${refusal ? ` ${refusal}` : ""} Open details.`}>
      <span>{percent(score)}</span>{sub}{lift !== undefined && lift !== null && <small className={lift < 0 ? "negative" : "lift"}>{pp(lift)}</small>}
    </button>
  </Hint><CornerMarks missing={note ? missing : 0} refusal={mark ? refusal : undefined} /></div>;
}
