"use client";

import { X } from "lucide-react";
import { checkCounts, checkKind, trialScore } from "../src/scoring";
import type { EvalCell, Trial } from "../src/board";
import { heat, percent } from "./scores";
import { updateQuery } from "./url-state";

export type TrialDisplay = "marks" | "numbers";
export const defaultTrialDisplay: TrialDisplay = "marks";
export const readTrialDisplay = (value: string | null): TrialDisplay =>
  value === "numbers" || value === "c" ? "numbers" : defaultTrialDisplay;
export const trialDisplayParam = (display: TrialDisplay) => display === "numbers" ? "&trial-display=numbers" : "";

export function TrialDisplayControl({ display }: { display: TrialDisplay }) {
  return <label className="trial-display"><span className="eyebrow">Prototype · Trial display</span>
    <select value={display} onChange={(event) => {
      const value = readTrialDisplay(event.target.value);
      updateQuery({ "trial-display": value === defaultTrialDisplay ? null : value });
    }}>
      <option value="marks">Marks</option>
      <option value="numbers">Numbers</option>
    </select>
  </label>;
}

type Mark = { kind: "score"; score: number } | { kind: "gate-check"; score: 0 } | { kind: "error"; score: null };

function trialMark(task: string, trial: Trial): Mark {
  const score = trialScore(task, trial, "gated");
  if (score === null) return { kind: "error", score };
  const { gates } = checkCounts(task, trial.checks);
  return gates.passed < gates.total ? { kind: "gate-check", score: 0 } : { kind: "score", score };
}

const checkName = (name: string) =>
  name.replace(/^test_/, "").replace(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ").toLowerCase();

function markLine(task: string, trial: Trial, mark: Mark) {
  if (mark.kind === "error") return "Error";

  const missed = Object.entries(trial.checks)
    .filter(([name, check]) => !check.passed && (mark.kind !== "gate-check" || checkKind(task, name) !== "judgment check"))
    .map(([name]) => checkName(name));
  const first = missed[0];
  const names = first && `${first.length > 46 ? first.slice(0, 45) + "…" : first}${missed.length > 1 ? ` +${missed.length - 1}` : ""}`;
  if (mark.kind === "gate-check") return `A gate check failed: ${names}`;

  const { counted, judgment } = checkCounts(task, trial.checks);
  if (task.startsWith("build/audit-") && judgment.total) return `Found ${judgment.passed} of ${judgment.total}`;
  return `${counted.total ? `${counted.passed} of ${counted.total} checks` : percent(mark.score)}${names ? ` · missed ${names}` : ""}`;
}

const markHint = (task: string, trial: Trial, mark: Mark) => `Trial ${trial.trial} · ${markLine(task, trial, mark)}`;
export const trialLine = (task: string, trial: Trial) => markLine(task, trial, trialMark(task, trial));

export function trialHint(task: string, trial: Trial, display?: TrialDisplay) {
  if (display) return markHint(task, trial, trialMark(task, trial));
  if (trial.status === "error") return "Trial ended in an error";
  const missed = Object.entries(trial.checks).filter(([, check]) => !check.passed);
  if (!missed.length) return "No checks missed";
  const first = checkName(missed[0][0]);
  return missed.length === 1 && first.length <= 32 ? `Missed ${first}` : `Missed ${missed.length} checks`;
}

function TrialMark({ mark }: { mark: Mark }) {
  return <span className="trial-mark" data-mark={mark.kind} style={heat(mark.score)} aria-hidden="true">
    {mark.kind === "gate-check" && <X size={11} strokeWidth={2.5} />}
    {mark.kind === "error" && "!"}
  </span>;
}

export function TrialLegend() {
  return <p className="trial-legend" aria-label="Trial mark legend">
    <span><TrialMark mark={{ kind: "score", score: 0.5 }} /> Filled to the trial score</span>
    <span><TrialMark mark={{ kind: "gate-check", score: 0 }} /> Gate check failed</span>
    <span><TrialMark mark={{ kind: "error", score: null }} /> Error</span>
  </p>;
}

export function taskMarkDetails(task: string, cell: EvalCell) {
  return cell.trials.map((trial) => ({ trial, mark: trialMark(task, trial) })).sort((a, b) =>
    (b.mark.score ?? -1) - (a.mark.score ?? -1) ||
    Number(a.mark.kind === "gate-check") - Number(b.mark.kind === "gate-check") ||
    a.trial.trial - b.trial.trial,
  ).map(({ trial, mark }) => ({ number: trial.trial, mark, hint: markHint(task, trial, mark) }));
}

export function TaskMarks({ details }: { details: ReturnType<typeof taskMarkDetails> }) {
  return <span className="task-marks">{details.map(({ number, mark }) =>
    <TrialMark key={number} mark={mark} />)}</span>;
}

function numberText(task: string, score: number, counts: ReturnType<typeof checkCounts>[]) {
  const findingsPerTrial = counts[0]?.judgment.total ?? 0;
  if (task.startsWith("build/audit-") && findingsPerTrial > 0 &&
      counts.every(({ gates, judgment }) => gates.passed === gates.total && judgment.total === findingsPerTrial)) {
    const found = counts.reduce((sum, { judgment }) => sum + judgment.passed, 0);
    return `${found} of ${counts.length * findingsPerTrial} found`;
  }
  return percent(score);
}

export function cellText(task: string, cell: EvalCell, display?: TrialDisplay) {
  if (cell.score === null) return "–";
  if (display !== "numbers") return display ? percent(cell.score) : `${cell.passed}/${cell.total}`;
  const counts = cell.trials.filter((trial) => trial.status !== "error").map((trial) => checkCounts(task, trial.checks));
  return numberText(task, cell.score, counts);
}

export function GatedTrialScore({ task, trial, display, heading }: {
  task: string; trial: Trial; display: TrialDisplay; heading?: boolean;
}) {
  const mark = trialMark(task, trial);
  if (display === "numbers") {
    const text = mark.score === null ? "Error" : numberText(task, mark.score, [checkCounts(task, trial.checks)]);
    return <span className="trial-score" data-error={mark.score === null || undefined} style={heat(mark.score)}>{text}</span>;
  }
  const hint = markHint(task, trial, mark);
  return <span className={heading ? "trial-heading-score" : undefined}>
    <TrialMark mark={mark} />
    {heading ? <span>{mark.score === null ? "Error" : percent(mark.score)}</span> : <span className="sr-only">{hint}</span>}
    {heading && mark.kind === "gate-check" && <span className="sr-only">Gate check failed</span>}
  </span>;
}
