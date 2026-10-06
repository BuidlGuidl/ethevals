"use client";
import type { CSSProperties } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
export const percent = (score: number | null) => score === null ? "–" : `${Math.round(score * 100)}%`;
export const money = (value: number | null, digits = 2) => value === null ? "–" : `$${value.toFixed(digits)}`;
export const pp = (value: number | null) => value === null ? "–" : `${Math.round(value) > 0 ? "+" : ""}${Math.round(value)}pp`;
export const heat = (score: number | null) => score === null ? undefined : { "--score": `${score * 100}%` } as CSSProperties;
export const formulas = {
  overall: "Overall = mean of scored pillar scores; pillars without a score are skipped.",
  pillar: "Pillar score = mean of scored eval pass rates; evals without scores are skipped.",
  eval: "Eval pass rate = passed epochs ÷ scored epochs; errors are excluded.",
  cost: "$ / pass = model cost of scored epochs ÷ passed epochs; no passes or missing prices show –.",
  lift: "Lift = mean change over evals scored in both modes for the same configuration, in percentage points. Overall averages paired pillar lifts.",
  tokens: "Tokens per run = median total model and grader tokens across scored epochs.",
};
export function Hint({ text, children }: { text: string; children: React.ReactElement }) {
  return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent className="whitespace-pre-line">{text}</TooltipContent></Tooltip>;
}
export function Score({ score, lift, onOpen, label, formula, empty = "No epochs yet", counts }: {
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
