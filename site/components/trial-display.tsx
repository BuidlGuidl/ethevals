import { AlertTriangle, ShieldBan } from "lucide-react";
import type { EvalCell, Trial } from "../src/board";
import { isRefusedTrial } from "../src/refusals";
import { percent } from "./scores";

export const entryLabels: Readonly<Record<string, string>> = {
  compile: "Did not compile", answered: "No answer", no_answer: "No answer", report_written: "No report",
};

const checkName = (name: string) =>
  name.replace(/^test_/, "").replace(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ").toLowerCase();

type State = "full" | "part" | "zero" | "error" | "refused";

export function trialState(trial: Trial): State {
  const { score } = trial;
  if (score.value === null) return "error";
  if (isRefusedTrial(trial)) return "refused";
  return score.value === 1 ? "full" : score.value === 0 ? "zero" : "part";
}

export function trialNote(trial: Trial): string {
  const { score } = trial;
  if (score.value === null) return "Error";
  if (isRefusedTrial(trial)) return trial.ignored ? "Refused (ignored)" : "Safety refusal";
  if (score.stop?.kind === "entry") return entryLabels[score.stop.name];
  if (score.stop?.kind === "gate") {
    const { name, more } = score.stop;
    return `Gate check failed: ${checkName(name)}${more ? ` and ${more} more` : ""}`;
  }
  return score.total ? `${score.passed} of ${score.total} passed` : "No checks counted";
}

export const trialScoreText = ({ score, ignored }: Trial) => score.value === null ? "Not scored" : ignored ? "Ignored" : percent(score.value);
export const trialHint = (trial: Trial) =>
  `Trial ${trial.trial} · ${trial.score.value === null || trial.ignored ? "" : `${trialScoreText(trial)} · `}${trialNote(trial)}`;
export const taskHint = (cell: EvalCell) =>
  [`Task score ${percent(cell.score)}`, ...cell.trials.map(trialHint)].join("\n");

export function TrialDot({ state, ignored }: { state: State; ignored?: boolean }) {
  return <span className="run-dot" data-state={state} data-ignored={ignored || undefined} aria-hidden="true">
    {state === "error" && <AlertTriangle size={12} strokeWidth={2.2} className="text-amber" />}
    {state === "refused" && <ShieldBan size={12} strokeWidth={2.2} className="text-refusal" />}
  </span>;
}

export function TrialDots({ trials }: { trials: Trial[] }) {
  return <span className="run-dots" role="img" aria-label={trials.map(trialHint).join(", ")}>
    {trials.map((trial) => <TrialDot key={trial.trial} state={trialState(trial)} ignored={trial.ignored} />)}
  </span>;
}

export function TrialLegend({ refused = false }: { refused?: boolean }) {
  return <p className="trial-legend" aria-label="Trial dot legend">
    <span><TrialDot state="full" /> 100%</span>
    <span><TrialDot state="part" /> Some checks missed</span>
    <span><TrialDot state="zero" /> 0%</span>
    <span><TrialDot state="error" /> Error</span>
    {refused && <span><TrialDot state="refused" /> Safety refusal</span>}
  </p>;
}
