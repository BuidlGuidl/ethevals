"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import {
  pillars, subjectKey,
  type BoardData, type Cell, type DisplayEvaluation as Evaluation, type TableMode as Mode, type Pillar, type Epoch, type Subject,
} from "../src/board";

const names: Record<Pillar, string> = {
  concepts: "Concepts", transactions: "Transactions", building: "Building", security: "Security",
};
const descriptions: Record<Pillar, string> = {
  concepts: "Ethereum knowledge and standards.",
  transactions: "Actions that change chain state.",
  building: "Code that works in its workspace.",
  security: "Risks in contracts and their use.",
};
const percent = (score: number) => `${Math.round(score * 100)}%`;
const money = (cost: number | null) => cost === null ? "Unknown" : `$${cost.toFixed(4)}`;
const countText = (cell: Cell) => `${cell.passed} of ${cell.total} epochs passed`;
const cellText = (cell: Cell) => cell.state === "na" ? "Not applicable"
  : cell.state === "empty" ? "No evals yet" : cell.state === "pending" ? "No epochs yet" : percent(cell.score!);
const subjectName = (subject: Subject) => [subject.model, subject.harness].filter(Boolean).join(" · ");

type Selection = { evaluation?: Evaluation; pillar: Pillar; subject: Subject; mode: Mode };

function Score({ cell, label, open }: {
  cell: Cell; label: string; open: () => void;
}) {
  const pillar = "scoredEvals" in cell;
  const tone = cell.score === null ? "" : cell.score < 0.25 ? "negative" : cell.score < 0.5 ? "caution" : "positive";
  return <button className="cell" onClick={open}
    aria-label={`${label}. ${cellText(cell)}.${cell.state === "score" ? ` ${countText(cell)}.` : ""} Open details.`}>
    <span className={cell.state === "score" ? `score ${tone}` : cell.state === "empty" ? "empty-pillar" : cell.state}>{cellText(cell)}</span>
    {cell.state === "score" && <>
      <span className="subline">{pillar ? `Mean of ${cell.scoredEvals} eval${cell.scoredEvals === 1 ? "" : "s"}` : countText(cell)}</span>
      {pillar && <span className="subline">{countText(cell)}</span>}
    </>}
    {cell.errors > 0 && <span className="error-note">{cell.errors} {cell.errors === 1 ? "error" : "errors"} excluded</span>}
  </button>;
}

function ResultsTable({ data, mode, onOpen }: { data: BoardData; mode: Mode; onOpen: (selection: Selection) => void }) {
  const [expanded, setExpanded] = useState<Pillar[]>(["concepts"]);
  const [column, setColumn] = useState<string | null>(null);
  const table = data.tables[mode];
  const subjects = table.subjects;
  const evaluations = pillars.flatMap((pillar) => table.pillars[pillar].evals.map((entry) => data.evaluations[entry.id]));
  const title = mode === "internet" ? "Agent table" : "Knowledge table";

  return <section className="board-section" id={mode === "internet" ? "agents" : "knowledge"} aria-label={title}>
    <div className="toolbar">
      <div><h2>{title}</h2><p className="muted">{mode === "internet"
        ? "Can I trust my agent with Ethereum?" : "What does a bare model know about Ethereum?"}</p></div>
      {/* The mode label is the reserved place for a future skills toggle. */}
      <div className="mode-label">{mode === "internet" ? "Internet · no Ethereum skills" : "Vanilla · no harness or tools"}</div>
    </div>
    {!subjects.length ? <div className="empty">
      <h3>{mode === "internet" ? "No agent epochs yet" : "No knowledge epochs yet"}</h3>
      <p>No published results match the current evals. Scores will appear after epochs finish.</p>
      <details><summary>Browse {evaluations.length} evals</summary><div className="catalog">
        {evaluations.map((evaluation) => <article key={evaluation.id}>
          <h3>{evaluation.title}</h3><p>{evaluation.motivation}</p>
          <p className="subline">{names[evaluation.pillar]} · {evaluation.type} · {evaluation.modes.join(", ")}</p>
          <details><summary>Read prompt</summary><Prompt evaluation={evaluation} /></details>
        </article>)}
      </div></details>
    </div> : <div className="table-shell">
      <div className="table-scroll" role="region" tabIndex={0} aria-label={`${title}. Scroll horizontally for all columns.`}>
        <table className="board" onMouseLeave={() => setColumn(null)} onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setColumn(null);
        }}>
          <caption className="sr-only">{title}. Pillars expand to evals. Open a cell for epochs and checks.</caption>
          <thead><tr>
            <th scope="col" className="row-label" onMouseEnter={() => setColumn(null)}>Pillar / eval<span className="subline">Expand a pillar to see its evals</span></th>
            {subjects.map((subject) => <th key={subjectKey(subject)} scope="col"
              className={column === subjectKey(subject) ? "column-hover" : ""}
              onMouseEnter={() => setColumn(subjectKey(subject))}>
              <span className="agent-name">{subject.model}</span>
              {subject.harness && <span className="subline">{subject.harness}</span>}
              <span className="subline">Effort: {subject.effort ?? "not recorded"}</span>
            </th>)}
          </tr></thead>
          {pillars.map((pillar) => {
            const pillarRow = table.pillars[pillar];
            const items = pillarRow.evals;
            const open = expanded.includes(pillar);
            const id = `${mode}-${pillar}`;
            return <Fragment key={pillar}>
              <tbody><tr className="pillar-row">
                <th scope="row" className="row-label" onMouseEnter={() => setColumn(null)}>
                  <button className="pillar-toggle" aria-expanded={open} aria-controls={id}
                    onClick={() => setExpanded(open ? expanded.filter((value) => value !== pillar) : [...expanded, pillar])}>
                    <svg className="chevron" viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden="true"><path d="m6 3 5 5-5 5" stroke="currentColor" strokeWidth="1.5" /></svg>
                    {names[pillar]}<span className="subline">{items.length} evals</span>
                  </button>
                </th>
                {subjects.map((subject) => <td key={subjectKey(subject)}
                  className={column === subjectKey(subject) ? "column-hover" : ""}
                  onMouseEnter={() => setColumn(subjectKey(subject))} onFocus={() => setColumn(subjectKey(subject))}>
                  <Score cell={pillarRow.cells[subjectKey(subject)]}
                    label={`${names[pillar]}, ${subjectName(subject)}`}
                    open={() => onOpen({ pillar, subject, mode })} />
                </td>)}
              </tr></tbody>
              <tbody id={id} hidden={!open}>
                {items.length ? items.map((entry) => { const evaluation = data.evaluations[entry.id]; return <tr key={evaluation.id} className="eval-row">
                  <th scope="row" className="row-label" onMouseEnter={() => setColumn(null)}>
                    {evaluation.title}<span className="eval-id">{evaluation.id}</span><span className="subline">{evaluation.type}</span>
                  </th>
                  {subjects.map((subject) => <td key={subjectKey(subject)}
                    className={column === subjectKey(subject) ? "column-hover" : ""}
                    onMouseEnter={() => setColumn(subjectKey(subject))} onFocus={() => setColumn(subjectKey(subject))}>
                    <Score cell={entry.cells[subjectKey(subject)]}
                      label={`${evaluation.title}, ${subjectName(subject)}`}
                      open={() => onOpen({ evaluation, pillar, subject, mode })} />
                  </td>)}
                </tr>; }) : <tr><td colSpan={subjects.length + 1} className="no-evals">No evals yet for this mode.</td></tr>}
              </tbody>
            </Fragment>;
          })}
        </table>
      </div>
      <div className="table-note">Open a cell for epochs and checks. A pillar score is the mean of its eval scores.</div>
    </div>}
  </section>;
}

function Prompt({ evaluation }: { evaluation: Evaluation }) {
  return <div className="prompt"><pre>{evaluation.prompt}</pre>
    {evaluation.choices.length > 0 && <ol type="A">{evaluation.choices.map((choice, index) => <li key={index}>{choice}</li>)}</ol>}
  </div>;
}

function Epochs({ rows, data }: { rows: Epoch[]; data: BoardData }) {
  const [selected, setSelected] = useState(0);
  const epoch = rows[selected];
  if (!epoch) return null;
  const href = epoch.logUrl;
  return <>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Epoch results. Scroll horizontally for all fields.">
      <table className="epoch-table"><caption className="sr-only">Epoch results and costs including the grader</caption>
        <thead><tr>{["Epoch", "Result", "Time", "Total tokens", "Cost", "Error or limit"].map((title) => <th scope="col" key={title}>{title}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => <tr key={row.epoch} className={index === selected ? "selected" : ""}>
          <th scope="row"><button aria-expanded={index === selected} aria-controls="epoch-checks" onClick={() => setSelected(index)}>Epoch {row.epoch}</button></th>
          <td className={row.status === "passed" ? "positive" : row.status === "failed" ? "negative" : "caution"}>{row.status === "passed" ? "Pass" : row.status === "failed" ? "Fail" : "Error"}</td>
          <td>{row.total_seconds === null ? "Unknown" : `${row.total_seconds.toFixed(1)}s`}</td>
          <td>{row.total_tokens.toLocaleString("en-US")}</td><td>{money(row.cost)}</td>
          <td className="epoch-issue">{row.issue || "None"}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <section id="epoch-checks" className="epoch-detail" aria-labelledby="epoch-title">
      <h3 id="epoch-title">Epoch {epoch.epoch}</h3>
      {epoch.error_reason && <p className="error-message">{epoch.error_kind ?? "Execution"} error: {epoch.error_reason}. This epoch does not count toward the score.</p>}
      <ul className="checks">{Object.entries(epoch.checks).map(([name, check]) => <li key={name}>
        <div><span className={check.passed ? "positive" : "negative"}>{check.passed ? "Pass" : "Fail"}</span><code>{name}</code></div><p>{check.reason}</p>
      </li>)}</ul>
      {!Object.keys(epoch.checks).length && <p className="muted">No checks completed.</p>}
      <p className="subline">Time includes setup. Total tokens include the model and grader.</p>
      <div className="cost-detail">
        <p>Model: <span className="mono">{money(epoch.model_cost_usd)}</span> <span className="muted">· {epoch.model_cost_source}</span></p>
        <p>Grader: <span className="mono">{money(epoch.grader_cost_usd)}</span> <span className="muted">· {epoch.grader_cost_source}</span></p>
      </div>
      {href ? <a href={href} target="_blank" rel="noreferrer">{data.sample ? "Open sample log" : "Open full log"}</a>
        : <p className="muted">Full log not published.</p>}
    </section>
  </>;
}

export function Detail({ selection, data, onSelect, onClose }: {
  selection: Selection; data: BoardData; onSelect: (selection: Selection) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    const opener = document.activeElement as HTMLElement | null;
    element.showModal();
    closeButton.current?.focus();
    return () => { element.close(); opener?.focus(); };
  }, []);
  useEffect(() => {
    dialog.current?.scrollTo(0, 0);
    closeButton.current?.focus();
  }, [selection]);
  const { evaluation, pillar, subject, mode } = selection;
  const pillarRow = data.tables[mode].pillars[pillar];
  const key = subjectKey(subject);
  const evalRow = evaluation ? pillarRow.evals.find((entry) => entry.id === evaluation.id) : undefined;
  const evalCell = evalRow?.cells[key];
  const cell = evalCell ?? pillarRow.cells[key];
  return <dialog ref={dialog} aria-labelledby="detail-title" onCancel={(event) => { event.preventDefault(); onClose(); }}
    onClick={(event) => {
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.target === event.currentTarget && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) onClose();
    }}>
    <header className="drawer-header"><div className="drawer-heading">
      <p className="subline">{names[pillar]} · {mode} · {subjectName(subject)}</p>
      <h2 id="detail-title">{evaluation?.title ?? names[pillar]}</h2>
      <p className="mono">{cellText(cell)}{cell.state === "score" && ` · ${countText(cell)}`}</p>
      {data.sample && <p className="sample-label">Sample data. Invented results.</p>}
    </div><button ref={closeButton} className="close-button" aria-label="Close details" onClick={onClose}>Close</button></header>
    <div className="drawer-content">
      {evaluation ? <>
        <button className="back-button" onClick={() => onSelect({ pillar, subject, mode })}>Back to {names[pillar].toLowerCase()} evals</button>
        <section><h3>Motivation</h3><p>{evaluation.motivation}</p></section>
        <section><h3>Prompt</h3><Prompt evaluation={evaluation} /></section>
        {cell.state === "na" && <p>This eval does not declare the {mode} mode.</p>}
        {cell.state === "pending" && <p>{cell.errors ? "No scored epochs yet. Errors do not count toward the score." : "No epochs yet for this eval."}</p>}
        {evalCell && <Epochs key={`${evaluation.id}-${subjectKey(subject)}-${mode}`} rows={evalCell.epochs} data={data} />}
      </> : <>
        <p>Each eval with scored epochs has equal weight. Missing and errored epochs never count as zero.</p>
        {cell.state === "score" && <p className="muted">{percent(cell.score!)} is the mean of {pillarRow.cells[key].scoredEvals} eval scores. The epoch count below each score adds their epochs together.</p>}
        <div className="eval-list">{pillarRow.evals.map((entry) => { const item = data.evaluations[entry.id]; return <button key={item.id} onClick={() => onSelect({ ...selection, evaluation: item })}>
          <span>{item.title}<span className="eval-id">{item.type} · {item.id}</span></span>
          <span className="mono">{cellText(entry.cells[key])}</span>
        </button>; })}</div>
        {cell.state === "empty" && <p>No evals yet for this mode.</p>}
      </>}
    </div>
  </dialog>;
}

export default function Board({ data }: { data: BoardData }) {
  const [selection, setSelection] = useState<Selection | null>(null);
  return <>
    <a className="skip-link" href="#main">Skip to results</a>
    <nav className="topnav" aria-label="Results tables"><a className="brand" href="#main">ETH Evals</a><a href="#agents">Agents</a><a href="#knowledge">Knowledge</a><a href="#scoring">How scoring works</a></nav>
    <main id="main">
      <header className="page-heading"><h1>Ethereum work, measured.</h1><p>How well agents do Ethereum work, and what bare models know.</p></header>
      {data.sample && <aside className="sample-banner"><strong>Sample data</strong><span>All results and extra evals on this page are invented. These are not model rankings.</span></aside>}
      <section className="pillar-strip" aria-label="Pillars">{pillars.map((pillar) => <div key={pillar}><h2>{names[pillar]}</h2><p>{descriptions[pillar]}</p></div>)}</section>
      <ResultsTable data={data} mode="internet" onOpen={setSelection} />
      <ResultsTable data={data} mode="vanilla" onOpen={setSelection} />
      <section id="scoring" className="scoring"><h2>How scoring works</h2>
        <p>An epoch passes when every named check passes. Each eval score is the share of scored epochs that passed.</p>
        <p>A pillar score is the mean of its eval scores. Evals without scored epochs do not enter the mean.</p>
        <p>Errors stay in the details but do not count toward scores. Time and token limits count as failures.</p>
        <p>Counts show how much evidence sits behind each score. No confidence interval is shown.</p>
        <div className="legend"><span><b>No evals yet</b> · the pillar has no evals for this mode</span><span><b>Not applicable</b> · the eval does not declare this mode</span><span><b>No epochs yet</b> · no scored epochs for this cell</span></div>
        <p className="subline">Only results for current eval hashes appear. Reference answers, empty answers, and other mock checks never enter the board.</p>
      </section>
      <footer>ETH Evals · Costs are in USD and include the model and grader. Unknown cost stays unknown.</footer>
      <noscript>The tables show their initial state. Enable JavaScript to expand pillars and open epoch details.</noscript>
    </main>
    {selection && <Detail selection={selection} data={data} onSelect={setSelection} onClose={() => setSelection(null)} />}
  </>;
}
