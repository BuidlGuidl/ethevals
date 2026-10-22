"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowDown, ArrowUp, Check, X, AlertTriangle } from "lucide-react";
import { agentLabel, modelLabel, modelOnlyNote, names, modeNames, unwrapPrompt } from "../src/labels";
import { pillars, agentKey, type BoardData, type Table, type DisplayEval as Eval, type Pillar, type Mode, type Trial, type Agent } from "../src/board";
import { decodeSelection, encodeSelection, type Selection } from "../src/selection";
import { Configuration } from "../components/configuration";
import { Logo } from "../components/logo";
import { ModeToggle } from "../components/mode-toggle";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { TooltipProvider } from "../components/ui/tooltip";
import { Score, Hint, formulas, heat, percent, money } from "../components/scores";
import { updateQuery, useQuery } from "../components/url-state";
import { repo } from "../components/shell";

type Sort = "overall" | Pillar | "costPerPass";
const verdictLabels = { passed: "PASS", failed: "FAIL", error: "ERROR" };

function Verdict({ trial }: { trial: Trial }) {
  return <span className={`verdict ${trial.status === "passed" ? "positive" : trial.status === "failed" ? "negative" : "caution"}`}>
    {trial.status === "passed" ? <Check size={14} /> : trial.status === "failed" ? <X size={14} /> : <AlertTriangle size={14} />}
    {verdictLabels[trial.status]}</span>;
}

const tokenFormat = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const tokens = (value: number) => tokenFormat.format(value).toLowerCase();
const duration = (trial: Trial) => trial.total_seconds === null ? "–" : `${trial.total_seconds.toFixed(1)}s`;

function EvalList({ table, evaluations, agent, pillar, onEval }: {
  table: Table; evaluations: BoardData["evaluations"]; agent: Agent; pillar?: Pillar; onEval: (evaluation: Eval) => void;
}) {
  const key = agentKey(agent);
  return <div className="eval-list">{pillars.filter((value) => !pillar || pillar === value).map((value) =>
    <section key={value}>{!pillar && <h3>{names[value]}</h3>}
      {table.pillars[value].evals.filter((entry) => entry.cells[key].state !== "na").map((entry) => {
        const evaluation = evaluations[entry.id], cell = entry.cells[key];
        return <button key={entry.id} className="eval-list-row" onClick={() => onEval(evaluation)}>
          <span className="eval-list-title"><b>{evaluation.title}</b><small>{evaluation.id}</small></span>
          <span className="run-dots" aria-label={cell.trials.map((trial) => `Trial ${trial.trial}: ${trial.status}`).join(", ")}>
            {cell.trials.map((trial) => <span key={trial.trial} className={`run-dot ${trial.status}`} />)}</span>
          <span className="heat-chip" data-empty={cell.score === null} style={heat(cell.score)}>{cell.passed}/{cell.total}</span>
        </button>;
      })}
      {table.pillars[value].cells[key].state === "empty" && <p className="muted">No tasks yet for this mode.</p>}
    </section>)}</div>;
}

function EvalView({ evaluation, trials, onRun }: { evaluation: Eval; trials: Trial[]; onRun: (run: number) => void }) {
  return <>
    <p className="why">{evaluation.description}</p>
    <details className="prompt-disclosure" open><summary>Instruction</summary><pre>{unwrapPrompt(evaluation.instruction)}</pre>
    </details>
    <section className="detail-section"><h3>Trials</h3>{trials.length ?
      <div className="table-shell"><div className="table-scroll" role="region" tabIndex={0} aria-label="Trials. Scroll horizontally for all columns.">
        <table className="runs-table"><caption className="sr-only">Trials for this task and configuration. Open a row for checks and trajectories.</caption>
          <thead><tr>{["Trial", "Result", "Checks", "Time", "Tokens", "Cost"].map((label) => <th scope="col" key={label}>{label}</th>)}<th scope="col"><span className="sr-only">Open trial</span></th></tr></thead>
          <tbody>{trials.map((trial) => {
            const checks = Object.values(trial.checks), passed = checks.filter((check) => check.passed).length;
            return <tr key={trial.trial}><td><button className="run-open" onClick={() => onRun(trial.trial)}
              aria-label={`Trial ${trial.trial}, ${verdictLabels[trial.status]}, ${passed} of ${checks.length} checks passed, ${duration(trial)}, ${tokens(trial.total_tokens)} tokens, ${money(trial.cost, 4)}. Open trial.`}>Trial {trial.trial}</button></td>
              <td><Verdict trial={trial} /></td><td>{passed}/{checks.length}</td><td>{duration(trial)}</td><td>{tokens(trial.total_tokens)}</td><td>{money(trial.cost, 4)}</td><td aria-hidden="true">›</td></tr>;
          })}</tbody></table>
      </div></div> : <p>No trials yet.</p>}
    </section>
  </>;
}

function RunView({ trial, trials, onRun }: { trial: Trial; trials: Trial[]; onRun: (run: number) => void }) {
  const checks = Object.entries(trial.checks);
  return <>
    <div className="run-switcher" role="group" aria-label="Trials">{trials.map((run) => <button key={run.trial}
      className={run.status === "passed" ? "positive" : run.status === "failed" ? "negative" : "caution"}
      aria-pressed={run.trial === trial.trial} aria-label={`Trial ${run.trial}: ${run.status}`} onClick={() => onRun(run.trial)}>
      Trial {run.trial} {run.status === "passed" ? "✓" : run.status === "failed" ? "✗" : "!"}</button>)}</div>
    <dl className="run-stats">{[
      ["Checks", `${checks.filter(([, check]) => check.passed).length} / ${checks.length}`],
      ["Tokens", tokens(trial.total_tokens)], ["Cost", money(trial.cost, 4)], ["Time", duration(trial)],
    ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {trial.issue && <p className="issue">{trial.error_kind ?? trial.limit?.type ?? "Trial"}: {trial.issue}</p>}
    {trial.status === "error" && <p className="caution">This error does not enter the score.</p>}
    {trial.limit && <p className="caution">{trial.limit.type} limit: {trial.limit.limit}{trial.limit.reason ? ` · ${trial.limit.reason}` : ""}</p>}
    <section className="verifier-verdict"><h3>Verifier checks</h3><ul className="checks">{checks.sort((a, b) => Number(a[1].passed) - Number(b[1].passed)).map(([name, check]) =>
      <li key={name}><span className={check.passed ? "positive" : "negative"}>{check.passed ? <Check size={16} /> : <X size={16} />}</span>
        <div><code>{name}</code><p>{check.reason}</p></div></li>)}</ul>
      {!checks.length && <p className="muted">No checks completed.</p>}
    </section>
    <p className="muted">{trial.paid_by === "free" ? "No model spend" : `Paid by ${trial.paid_by === "plan" ? "plan" : "API key"}`} · Cost at API prices</p>
    {trial.trajectoryUrl ? <div className="trajectory-links"><a className="button" href={trial.trajectoryUrl} target="_blank" rel="noreferrer">{trial.trajectoryUrl.startsWith("https://hub.harborframework.com/jobs/") ? "Open full trial on Harbor Hub ↗" : "Open trajectory ↗"}</a></div> : <p className="muted">Trajectory not published.</p>}
  </>;
}

export function Detail({ selection, data, onSelect }: {
  selection: Selection; data: BoardData; onSelect: (selection: Selection) => void;
}) {
  const { evaluation, pillar, agent, mode, fromList } = selection;
  const table = data.tables[mode], key = agentKey(agent), summary = table.summaries[key];
  const cell = evaluation ? table.pillars[evaluation.pillar].evals.find((entry) => entry.id === evaluation.id)?.cells[key] : undefined;
  const trials = cell?.trials ?? [], trial = trials.find((value) => value.trial === selection.run);
  const runLevel = trial !== undefined;
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.closest(".sheet")?.scrollTo({ top: 0 });
    heading.current?.focus({ preventScroll: true });
  }, [evaluation?.id, runLevel]);
  const scope = pillar ? table.pillars[pillar].cells[key] : summary;
  return <div className="detail-body">
    <header className="drawer-header"><h1 ref={heading} tabIndex={-1} className={trial ? "run-heading" : undefined}>{trial ? <>Trial {trial.trial} of {trials.length} <Verdict trial={trial} /></> : evaluation?.title ?? (pillar ? names[pillar] : "All pillars")}</h1>
      {trial && <p>{evaluation!.title}</p>}
      <Configuration agent={agent} /><p className="muted">{modeNames[mode]}</p>
      {!evaluation && <p>{percent(summary.scores[pillar ?? "overall"])} · {scope.passed}/{scope.total} scored · {scope.errors} errors excluded</p>}
      {!evaluation && summary.scores[pillar ?? "overall"] === null && <p className="muted">{pillar && table.pillars[pillar].cells[key].state === "empty" ? "No tasks yet" : "No trials yet"}</p>}
    </header>
    {trial ? <button className="back-button" onClick={() => onSelect({ ...selection, run: undefined })}><ArrowLeft size={14} />All trials</button>
      : evaluation && fromList && <button className="back-button" onClick={() => onSelect({ agent, mode, pillar })}>
        <ArrowLeft size={14} />{pillar ? names[pillar] : "All pillars"}</button>}
    {trial ? <RunView trial={trial} trials={trials} onRun={(run) => onSelect({ ...selection, run })} /> :
      evaluation ? <EvalView evaluation={evaluation} trials={trials} onRun={(run) => onSelect({ ...selection, run })} /> :
      <EvalList table={table} evaluations={data.evaluations} agent={agent} pillar={pillar}
        onEval={(value) => onSelect({ ...selection, evaluation: value, fromList: true })} />}
  </div>;
}

export default function Board({ data }: { data: BoardData }) {
  const query = useQuery();
  return <Results data={data} query={query} />;
}

export function Results({ data, query }: { data: BoardData; query: URLSearchParams }) {
  const mode: Mode = query.get("mode") === "skills" ? "skills" : query.get("mode") === "vanilla" ? "vanilla" : "internet";
  const evalsMode: Mode = query.get("evals") === "skills" ? "skills" : query.get("evals") === "vanilla" ? "vanilla" : "internet";
  const [sort, setSort] = useState<{ key: Sort; ascending: boolean }>({ key: "overall", ascending: false });
  const pushed = useRef(false);
  const opener = useRef<HTMLElement | null>(null);
  const selection = decodeSelection(query, data);
  useEffect(() => { if (!selection) opener.current?.focus({ preventScroll: true }); }, [selection]);
  const table = data.tables[mode];
  const matrixTable = data.tables[evalsMode];
  const changeMode = (value: Mode) => updateQuery({ mode: value });
  const select = (value: Selection) => {
    if (!selection) { pushed.current = true; opener.current = document.activeElement as HTMLElement | null; }
    updateQuery({ d: encodeSelection(value) }, !selection);
  };
  const close = () => {
    if (pushed.current) { pushed.current = false; window.history.back(); }
    else updateQuery({ d: null });
  };
  const value = (agent: Agent, key: Sort) => key === "costPerPass"
    ? table.summaries[agentKey(agent)].costPerPass : table.summaries[agentKey(agent)].scores[key];
  const agents = [...table.agents].sort((a, b) => {
    const x = value(a, sort.key), y = value(b, sort.key);
    return x === null ? y === null ? agentKey(a).localeCompare(agentKey(b)) : 1 : y === null ? -1 : (sort.ascending ? 1 : -1) * (x - y) || agentKey(a).localeCompare(agentKey(b));
  });
  const columns: [Sort, string][] = [["overall", "Overall"], ...pillars.map((pillar): [Sort, string] => [pillar, names[pillar]]), ["costPerPass", "$ / pass"]];
  const matrixAgents = [...matrixTable.agents].sort((a, b) =>
    (data.tables[evalsMode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(b)].scores.overall ?? -1) -
    (data.tables[evalsMode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(a)].scores.overall ?? -1));
  return <TooltipProvider delayDuration={200}><main id="main" className="page">
    {data.demo && <aside className="banner"><strong>Demo data</strong> · Invented results for a board preview.</aside>}
    <header className="hero"><div className="hero-brand"><h1 id="hero-logo" aria-label="ETH Evals"><Logo id="hero-gradient" /></h1>
      <p className="hero-plate"><span><b>{data.counts.evals}</b> tasks</span><span><b>{data.counts.agents}</b> agents</span><span><b>{data.counts.runs.toLocaleString("en")}</b> trials</span></p></div>
      <p className="hero-tag">The Open Benchmark for AI on Ethereum</p>
      <p className="hero-desc">We test AI agents, and the models behind them, on real Ethereum work. Every task, trial and trajectory is public, allowing anyone to run the same tasks.</p>
      <p className="hero-desc">We evaluate <Link href="/how-it-works/#hw-pillars">four pillars</Link>: <b>Concepts</b>, <b>Transactions</b>, <b>Building</b> and <b>Security</b>.</p>
    </header>
    <section id="leaderboard" className="results-section"><div className="section-head"><div><h2>Results</h2><p>The same work, with and without Ethereum skills.</p></div>
      <Link className="text-link" href={`/compare/?mode=${mode}`}>Compare configurations →</Link></div>
      <div className="toolbar"><ModeToggle mode={mode} onChange={changeMode} />{mode === "vanilla" && <p className="mode-note">{modelOnlyNote}</p>}</div>
      {agents.length ? <div className="table-shell"><div className="table-scroll" role="region" tabIndex={0} aria-label="Leaderboard. Scroll horizontally for all columns.">
        <table className="leaderboard"><caption className="sr-only">Configuration scores, sorted by {sort.key} {sort.ascending ? "ascending" : "descending"}</caption>
          <colgroup><col className="config-col" />{columns.map(([key]) => <col key={key} className="score-col" />)}</colgroup>
          <thead><tr><th scope="col" className="row-label">{mode === "vanilla" ? "Model" : "Configuration"}<small>model · agent</small></th>
            {columns.map(([key, name]) => <th key={key} scope="col" aria-sort={sort.key === key ? sort.ascending ? "ascending" : "descending" : "none"}>
              <button className="sort-button" onClick={() => setSort({ key, ascending: sort.key === key ? !sort.ascending : key === "costPerPass" })}>{name}{sort.key === key && (sort.ascending ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
            </th>)}</tr></thead><tbody>{agents.map((agent) => <tr key={agentKey(agent)}><th scope="row" className="row-label"><Configuration agent={agent} /></th>
              {columns.map(([key]) => <td key={key}>{key === "costPerPass" ? <Hint text={formulas.cost}><span className="cost-value">{money(value(agent, key))}</span></Hint> :
                <Score score={value(agent, key)} lift={mode === "skills" ? data.lifts[agentKey(agent)]?.[key] : undefined}
                  formula={key === "overall" ? formulas.overall : formulas.pillar}
                  label={`${key === "overall" ? "Overall" : names[key]}, ${agentLabel(agent)}`}
                  empty={key !== "overall" && table.pillars[key].cells[agentKey(agent)].state === "empty" ? "No tasks yet" : "No trials yet"}
                  onOpen={() => select({ agent, mode, pillar: key === "overall" ? undefined : key })} />}</td>)}
            </tr>)}</tbody></table></div>{mode === "skills" && <div className="table-note">+pp is the change over Internet.</div>}</div> :
        <div className="empty"><h3>{mode === "vanilla" ? "No model trials yet" : "No agent trials yet"}</h3><p>No published results match the current tasks. Browse the task catalog below.</p></div>}
      <div className="read-note" id="scoring"><b>How to read it:</b> Each row is an agent or a model, scored on the four pillars of Ethereum work. Overall is the average of the pillar scores. Click a pillar cell to see its tasks and every trial behind them.</div>
    </section>
    <section id="evals" className="results-section"><div className="section-head"><div><h2>Results by task · {modeNames[evalsMode]}</h2><p>A detailed view of the Leaderboard. See how many trials each agent passed on every task, grouped by pillar.</p></div>
      <ModeToggle mode={evalsMode} onChange={(value) => updateQuery({ evals: value })} label="Which task results" />
      <a className="button" href={`${repo}/blob/main/docs/add-a-task.md`} target="_blank" rel="noreferrer">How to add a task ↗</a></div>
      <p className="eyebrow">{pillars.reduce((sum, pillar) => sum + matrixTable.pillars[pillar].evals.length, 0)} tasks · {modeNames[evalsMode]}</p>
      <div className="table-shell"><div className="matrix-title">Task matrix · {modeNames[evalsMode]}</div><div className="table-scroll matrix-scroll" role="region" tabIndex={0} aria-label="Task matrix. Scroll for more configurations.">
        <table className="matrix"><caption className="sr-only">Passed trials / scored trials for each task and configuration</caption><thead><tr><th className="row-label" scope="col">Task</th>
          {matrixAgents.map((agent) => <th key={agentKey(agent)} scope="col"><Configuration agent={agent} /></th>)}</tr></thead>
          <tbody>{pillars.map((pillar) => <Fragment key={pillar}><tr className="pillar-band"><th scope="colgroup" colSpan={matrixAgents.length + 1}><span className="band-label">{names[pillar]}<small>{matrixTable.pillars[pillar].evals.length} tasks</small></span></th></tr>
            {matrixTable.pillars[pillar].evals.length ? matrixTable.pillars[pillar].evals.map((entry) => <tr key={entry.id} id={`eval-${entry.id.replaceAll("/", "-")}`}>
              <th scope="row" className="row-label"><span className="eval-title">{data.evaluations[entry.id].title}</span><small>{entry.id}</small></th>
              {matrixAgents.map((agent) => { const cell = entry.cells[agentKey(agent)];
                return <td key={agentKey(agent)}>{cell.state === "na" || cell.score === null ?
                  <span className="matrix-cell" data-empty title={cell.state === "na" ? "Not applicable" : cell.errors ? `${cell.errors} errors; no scored trials` : "No trials yet"}>–</span> :
                  <Hint text={formulas.eval}><button className="matrix-cell" style={heat(cell.score)}
                    aria-label={`${data.evaluations[entry.id].title}, ${modelLabel(agent.model)}: ${cell.passed} of ${cell.total} trials passed. Open details.`}
                    onClick={() => select({ evaluation: data.evaluations[entry.id], agent, mode: evalsMode })}>{cell.passed}/{cell.total}</button></Hint>}</td>;
              })}
            </tr>) : <tr><td colSpan={matrixAgents.length + 1} className="no-evals"><span className="band-label">No tasks yet</span></td></tr>}
          </Fragment>)}</tbody></table></div><div className="table-note">Trials passed per task. Click a scored cell for its instruction and trials. Errors are excluded from counts.</div></div>
    </section>
    <noscript>Enable JavaScript to change modes and open trial details.</noscript>
  </main>
    <Sheet open={selection !== null} onOpenChange={(open) => { if (!open) close(); }}>
      {selection && <SheetContent>
        <SheetTitle className="sr-only">Task and trial details</SheetTitle><SheetDescription className="sr-only">Scores, instructions, checks, costs and trajectories.</SheetDescription>
        <Detail selection={selection} data={data} onSelect={select} /></SheetContent>}
    </Sheet>
  </TooltipProvider>;
}
