"use client";
import { useState, type CSSProperties } from "react";
import { Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { scoringCopy } from "../src/labels";
import { defaultScoring, type Scoring } from "../src/scoring";
export const percent = (score: number | null) => score === null ? "–" : `${Math.round(score * 100)}%`;
export const money = (value: number | null, digits = 2) => value === null ? "–" : `$${value.toFixed(digits)}`;
export const pp = (value: number | null) => value === null ? "–" : `${Math.round(value) > 0 ? "+" : ""}${Math.round(value)}pp`;
export const heat = (score: number | null) => score === null ? undefined : { "--score": `${score * 100}%` } as CSSProperties;
export const formulas = {
  overall: "Overall = mean of scored pillar scores; pillars without a score are skipped.",
  pillar: "Pillar score = mean of scored task pass rates; tasks without scores are skipped.",
  eval: "Task pass rate = passed trials ÷ scored trials; errors are excluded.",
  matrixIntro: "A detailed view of the Leaderboard. See how many trials each agent passed on every task, grouped by pillar.",
  matrixCaption: "Passed trials / scored trials for each task and configuration",
  matrixNote: "Trials passed per task. Click a scored cell for its instruction and trials. Errors are excluded from counts.",
  lift: "Lift = mean change over tasks scored in both modes for the same configuration, in percentage points. Overall averages paired pillar lifts.",
};
export const formulasFor = (scoring: Scoring) => scoring === defaultScoring ? formulas : { ...formulas, ...scoringCopy.formulas };
export function Hint({ text, children }: { text: string; children: React.ReactElement }) {
  return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent className="whitespace-pre-line">{text}</TooltipContent></Tooltip>;
}
// Touch screens have no hover, so a tap opens the note too. preventDefault skips Radix's close on click.
export function InfoHint({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false);
  return <TooltipProvider delayDuration={200}><Tooltip open={open} onOpenChange={setOpen} disableHoverableContent><TooltipTrigger asChild>
    <button type="button" className="info-hint" aria-label={`${label}: ${text}`} onClick={(event) => { event.preventDefault(); setOpen(true); }}>
      <Info size={14} aria-hidden="true" /></button>
  </TooltipTrigger><TooltipContent className="max-w-80">{text}</TooltipContent></Tooltip></TooltipProvider>;
}
export function Score({ score, lift, onOpen, label, formula, empty = "No trials yet", counts }: {
  score: number | null; lift?: number | null; onOpen: () => void; label: string;
  formula: string; empty?: string; counts?: string;
}) {
  return <Hint text={`${formula}${lift !== undefined && lift !== null ? `\n${formulas.lift}` : ""}`}>
    <button className="score-cell" data-empty={score === null} style={heat(score)} onClick={onOpen}
      aria-label={`${label}. ${score === null ? empty : percent(score)}.${counts ? ` ${counts}.` : ""} Open details.`}>
      <span>{percent(score)}</span>{lift !== undefined && lift !== null && <small className={lift < 0 ? "negative" : "lift"}>{pp(lift)}</small>}
    </button>
  </Hint>;
}
