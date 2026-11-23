"use client";

import { Fragment, useMemo, type ReactNode } from "react";
import { scoreBoard, type BoardData } from "../src/board";
import { scoringCopy } from "../src/labels";
import { checkCounts, checkKind, defaultScoring, readScoring, scorings, trialScore, type Scoring } from "../src/scoring";
import { percent } from "./scores";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { updateQuery } from "./url-state";

export function useScoredBoard(data: BoardData, query: URLSearchParams): BoardData {
  const scoring = readScoring(query.get("scoring"));
  return useMemo(() => scoreBoard(data, scoring), [data, scoring]);
}

export const scoringParam = (scoring: Scoring) => scoring === defaultScoring ? "" : `&scoring=${scoring}`;

const withCode = (text: string) => text.split("`").map((part, index) =>
  index % 2 ? <code key={index}>{part}</code> : <Fragment key={index}>{part}</Fragment>);

const example = scoringCopy.example;
const exampleTrial = {
  status: "failed" as const,
  checks: Object.fromEntries(example.checks.map((check) => [check.name, { passed: check.passed, reason: "" }])),
};

function Example({ scoring }: { scoring: Scoring }) {
  const { counted } = checkCounts(example.task, exampleTrial.checks);
  const score = percent(trialScore(example.task, exampleTrial, scoring));
  const gated = scoring === "gated";
  return <div className="scoring-example"><p className="eyebrow">Example</p><p><code>token-governor</code></p>
    <table><tbody>{example.checks.map((check) => {
      const kind = checkKind(example.task, check.name);
      return <tr key={check.name}>
        <td className={check.passed ? "positive" : "negative"}>{check.passed ? "✓ pass" : "✗ fail"}</td>
        <td>{check.label}{gated && <small className="check-kind">{kind === "entry" ? "Gate · entry" : kind === "gate" ? "Gate" : "Judgment check"}</small>}</td>
      </tr>;
    })}</tbody></table>
    <p className="scoring-result">{gated
      ? `All gates passed. ${counted.passed} of ${counted.total} counted checks passed. Trial score ${score}.`
      : `One check failed. Trial score ${score}.`}</p>
  </div>;
}

export function ScoringToggle({ scoring, prototypeControl }: { scoring: Scoring; prototypeControl?: ReactNode }) {
  return <section className="scoring-panel" aria-label="How scores are calculated">
    <div className="scoring-switch"><span className="eyebrow">{scoringCopy.label}</span>
      <ToggleGroup type="single" value={scoring} aria-label={scoringCopy.label} className="[&>*+*]:border-l [&>*+*]:border-border-strong"
        onValueChange={(value) => { if (value) updateQuery({ scoring: value === defaultScoring ? null : value }); }}>
        {scorings.map((value) => <ToggleGroupItem key={value} value={value}>{scoringCopy.names[value]}</ToggleGroupItem>)}
      </ToggleGroup>{prototypeControl}</div>
    <div className="scoring-body">
      <div><p className="eyebrow">Rule</p><p className="scoring-rule">{scoringCopy.rule[scoring]}</p>
        {scoring === "gated" && <p className="mt-2 text-muted">{withCode(scoringCopy.entry)}</p>}</div>
      <Example scoring={scoring} />
      <div className="scoring-average"><p className="eyebrow">How scores average</p>
        <ul>{scoringCopy.average.map((line) => <li key={line}>{line}</li>)}</ul></div>
    </div>
  </section>;
}
