"use client";

import { Fragment, useMemo } from "react";
import { scoreBoard, type BoardData } from "../src/board";
import { scoringCopy } from "../src/labels";
import { checkPoints, defaultScoring, readScoring, scorings, trialScore, type Scoring } from "../src/scoring";
import { percent } from "./scores";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { updateQuery } from "./url-state";

// The one place a page reads the scoring version. Everything below it gets an already scored board.
export function useScoredBoard(data: BoardData, query: URLSearchParams): BoardData {
  const scoring = readScoring(query.get("scoring"));
  return useMemo(() => scoreBoard(data, scoring), [data, scoring]);
}

// Appended to links between Results and Compare. Empty for all or nothing, so default links match the live board.
export const scoringParam = (scoring: Scoring) => scoring === defaultScoring ? "" : `&scoring=${scoring}`;

// Backticks in the copy mark check and task names.
const withCode = (text: string) => text.split("`").map((part, index) => index % 2 ? <code key={index}>{part}</code> : <Fragment key={index}>{part}</Fragment>);

// The example trial, scored by the same code as the board, so its numbers cannot drift from the page's.
const example = scoringCopy.example;
const exampleTrial = {
  status: example.checks.every((check) => check.passed) ? "passed" as const : "failed" as const,
  checks: Object.fromEntries(example.checks.map((check) => [check.name, { passed: check.passed, reason: "" }])),
};
const exampleScore = (scoring: Scoring) => percent(trialScore(example.task, exampleTrial, scoring));

function Example({ scoring }: { scoring: Scoring }) {
  const points = scoring === "weighted" ? checkPoints(example.task, example.checks.map((check) => check.name), scoring) : null;
  const passed = example.checks.filter((check) => check.passed);
  const earned = passed.map((check) => points?.[check.name] ?? 0);
  const values: Record<string, string | number> = {
    failed: example.checks.length - passed.length, passed: passed.length, total: example.checks.length,
    sum: earned.join(" + "), earned: earned.reduce((sum, value) => sum + value, 0),
    possible: Object.values(points ?? {}).reduce((sum, value) => sum + value, 0), score: exampleScore(scoring),
  };
  return <div className="scoring-example"><p className="eyebrow">{scoringCopy.parts.example}</p><p>{withCode(example.title)}</p>
    <table><tbody>{example.checks.map((check) => <tr key={check.name}>
      <td className={check.passed ? "positive" : "negative"}>{check.passed ? "✓ pass" : "✗ fail"}</td><td>{check.label}</td>
      {points && <td className="scoring-points" data-zero={points[check.name] === 0 || undefined}>{points[check.name]} {points[check.name] === 1 ? "point" : "points"}</td>}</tr>)}</tbody></table>
    <p className="scoring-result">{withCode(example.result[scoring].replace(/\{(\w+)\}/g, (_, key: string) => String(values[key])))}</p>
    <p className="eyebrow">{scoringCopy.parts.versions}</p>
    <dl className="scoring-versions">{scorings.map((value) => <div key={value} data-selected={value === scoring || undefined}>
      <dt>{scoringCopy.names[value]}</dt><dd>{exampleScore(value)}</dd></div>)}</dl>
  </div>;
}

export function ScoringToggle({ scoring }: { scoring: Scoring }) {
  const detail = scoringCopy.detail[scoring], caveat = scoringCopy.caveat[scoring];
  return <section className="scoring-panel" aria-label="How scores are calculated">
    <div className="scoring-switch"><span className="eyebrow">{scoringCopy.label}</span>
      <ToggleGroup type="single" value={scoring} aria-label={scoringCopy.label} className="[&>*+*]:border-l [&>*+*]:border-border-strong"
        onValueChange={(value) => { if (value) updateQuery({ scoring: value === defaultScoring ? null : value }); }}>
        {scorings.map((value) => <ToggleGroupItem key={value} value={value}>{scoringCopy.names[value]}</ToggleGroupItem>)}
      </ToggleGroup><p className="muted">{scoringCopy.comparison}</p></div>
    <div className="scoring-body">
      <div><p className="eyebrow">{scoringCopy.parts.rule}</p><p className="scoring-rule">{withCode(scoringCopy.rule[scoring])}</p>
        {detail && <ul>{detail.map((line) => <li key={line}>{withCode(line)}</li>)}</ul>}</div>
      <Example scoring={scoring} />
      <div><p className="eyebrow">{scoringCopy.parts.caveat}</p><p>{withCode(caveat.lead)}</p>
        {caveat.list && <ul>{caveat.list.map((line) => <li key={line}>{withCode(line)}</li>)}</ul>}
        {caveat.close && <p className="mt-2">{withCode(caveat.close)}</p>}</div>
      <div className="scoring-average"><p className="eyebrow">{scoringCopy.parts.then}</p><ul>{scoringCopy.then.map((line) => <li key={line}>{line}</li>)}</ul></div>
    </div>
  </section>;
}
