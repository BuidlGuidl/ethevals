"use client";

import { Fragment, useMemo } from "react";
import { scoreBoard, type BoardData } from "../src/board";
import { scoringCopy } from "../src/labels";
import { defaultScoring, readScoring, scorings, type Scoring } from "../src/scoring";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { updateQuery } from "./url-state";

// The one place a page reads the scoring version. Everything below it gets an already scored board.
export function useScoredBoard(data: BoardData, query: URLSearchParams): BoardData {
  const scoring = readScoring(query.get("scoring"));
  return useMemo(() => scoreBoard(data, scoring), [data, scoring]);
}

// Appended to links between Results and Compare. Empty for all or nothing, so default links match the live board.
export const scoringParam = (scoring: Scoring) => scoring === defaultScoring ? "" : `&scoring=${scoring}`;

// Backticks in the copy mark check names.
const withCode = (text: string) => text.split("`").map((part, index) => index % 2 ? <code key={index}>{part}</code> : <Fragment key={index}>{part}</Fragment>);

export function ScoringToggle({ scoring }: { scoring: Scoring }) {
  return <section className="scoring-panel" aria-label="How scores are calculated">
    <div className="scoring-switch"><span className="eyebrow">{scoringCopy.label}</span>
      <ToggleGroup type="single" value={scoring} aria-label={scoringCopy.label} className="[&>*+*]:border-l [&>*+*]:border-border-strong"
        onValueChange={(value) => { if (value) updateQuery({ scoring: value === defaultScoring ? null : value }); }}>
        {scorings.map((value) => <ToggleGroupItem key={value} value={value}>{scoringCopy.names[value]}</ToggleGroupItem>)}
      </ToggleGroup></div>
    <div className="scoring-notes"><p><b>{scoringCopy.comparison}</b></p><p>{withCode(scoringCopy.notes[scoring])}</p><p>{withCode(scoringCopy.examples[scoring])}</p><p className="muted">{scoringCopy.shared}</p></div>
  </section>;
}
