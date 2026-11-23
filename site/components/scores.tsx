"use client";
import type { CSSProperties } from "react";
import { Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
export const percent = (score: number | null) => score === null ? "–" : `${Math.round(score * 100)}%`;
export const money = (value: number | null, digits = 2) => value === null ? "–" : `$${value.toFixed(digits)}`;
export const pp = (value: number | null) => value === null ? "–" : `${Math.round(value) > 0 ? "+" : ""}${Math.round(value)}pp`;
export const heat = (score: number | null) => score === null ? undefined : { "--score": `${score * 100}%` } as CSSProperties;
export const formulas = {
  overall: "Overall = mean of scored pillar scores; pillars without a score are skipped.",
  pillar: "Pillar score = mean of scored task pass rates; tasks without scores are skipped.",
  eval: "Task pass rate = passed trials ÷ scored trials; errors are excluded.",
  lift: "Lift = mean change over tasks scored in both modes for the same configuration, in percentage points. Overall averages paired pillar lifts.",
};
export const unscored = (count: number) => `${count} ${count === 1 ? "trial has" : "trials have"} no score yet.`;
export function Hint({ text, children }: { text: string; children: React.ReactElement }) {
  return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent className="whitespace-pre-line">{text}</TooltipContent></Tooltip>;
}
// Sits in the corner of a score that still has planned trials without a score.
export function Unscored({ count }: { count: number }) {
  return <Hint text={unscored(count)}><span className="unscored-info" role="img" aria-label={unscored(count)}><Info aria-hidden="true" /></span></Hint>;
}
export function Score({ score, lift, onOpen, label, formula, empty = "No trials yet", counts, missing = 0 }: {
  score: number | null; lift?: number | null; onOpen: () => void; label: string;
  formula: string; empty?: string; counts?: string; missing?: number;
}) {
  const note = score !== null && missing > 0 ? unscored(missing) : "";
  return <div className="score-wrap"><Hint text={`${formula}${lift !== undefined && lift !== null ? `\n${formulas.lift}` : ""}`}>
    <button className="score-cell" data-empty={score === null} style={heat(score)} onClick={onOpen}
      aria-label={`${label}. ${score === null ? empty : percent(score)}.${counts ? ` ${counts}.` : ""}${note && ` ${note}`} Open details.`}>
      <span>{percent(score)}</span>{lift !== undefined && lift !== null && <small className={lift < 0 ? "negative" : "lift"}>{pp(lift)}</small>}
    </button>
  </Hint>{note && <Unscored count={missing} />}</div>;
}
