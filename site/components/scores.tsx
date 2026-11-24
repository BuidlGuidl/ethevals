"use client";
import { useState, type CSSProperties, type ReactNode } from "react";
import { Info, ShieldBan } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { sentences } from "../src/refusals";
export const percent = (score: number | null) => score === null ? "–" : `${Math.round(score * 100)}%`;
export const money = (value: number | null, digits = 2) => value === null ? "–" : `$${value.toFixed(digits)}`;
export const pp = (value: number | null) => value === null ? "–" : `${Math.round(value) > 0 ? "+" : ""}${Math.round(value)}pp`;
export const heat = (score: number | null) => score === null ? undefined : { "--score": `${score * 100}%` } as CSSProperties;
// One sentence per line, so a tooltip never runs ideas together.
export const formulas = {
  overall: ["Overall averages pillar scores.", "Pillars without a score are skipped."],
  pillar: ["Pillar scores average task scores.", "Tasks without a score are skipped."],
  lift: ["Lift = mean change over tasks scored in both modes for the same configuration, in percentage points.", "Overall averages paired pillar lifts."],
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
  return <Hint text={unscored(count)}><span className="unscored-info" role="img" aria-label={unscored(count)}><Info aria-hidden="true" /></span></Hint>;
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
export function Score({ score, lift, onOpen, label, formula, empty = "No trials yet", missing = 0, refusal, sub }: {
  score: number | null; lift?: number | null; onOpen: () => void; label: string;
  formula: string[]; empty?: string; missing?: number;
  // Refusal lines show on the shield icon tooltip; `sub` adds a line under the score.
  refusal?: string[]; sub?: ReactNode;
}) {
  const note = score !== null && missing > 0 ? unscored(missing) : "";
  const hasLift = lift !== undefined && lift !== null;
  return <div className="score-wrap"><Hint text={[...formula, ...(hasLift ? formulas.lift : [])]}>
    <button className="score-cell" data-empty={score === null} style={heat(score)} onClick={onOpen}
      aria-label={`${label}. ${score === null ? empty : percent(score)}.${note && ` ${note}`}${refusal ? ` ${sentences(refusal)}` : ""} Open details.`}>
      <span>{percent(score)}</span>{sub}{hasLift && <small className={lift < 0 ? "negative" : "lift"}>{pp(lift)}</small>}
    </button>
  </Hint><CornerMarks missing={note ? missing : 0} refusal={refusal} /></div>;
}
