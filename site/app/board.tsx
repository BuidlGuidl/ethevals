"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowDown, ArrowUp, Check, X, AlertTriangle } from "lucide-react";
import { agentLabel, modelLabel, names, modeNames } from "../src/labels";
import { pillars, agentKey, type BoardData, type Table, type DisplayEval as Eval, type Pillar, type Mode, type Epoch, type Agent } from "../src/board";
import { decodeSelection, type Selection } from "../src/selection";
import { Configuration } from "../components/configuration";
import { Logo } from "../components/logo";
import { ModeToggle } from "../components/mode-toggle";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { TooltipProvider } from "../components/ui/tooltip";
import { Score, Hint, formulas, heat, percent, money } from "../components/scores";
import { updateQuery, useQuery } from "../components/url-state";
import { repo } from "../components/shell";

type Sort = "overall" | Pillar | "costPerPass";

function Verdict({ epoch }: { epoch: Epoch }) {
  return <span className={`verdict ${epoch.status === "passed" ? "positive" : epoch.status === "failed" ? "negative" : "caution"}`}>
    {epoch.status === "passed" ? <Check size={14} /> : epoch.status === "failed" ? <X size={14} /> : <AlertTriangle size={14} />}
    {epoch.status === "passed" ? "Pass" : epoch.status === "failed" ? "Fail" : "Error"}</span>;
}

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
          <span className="run-dots" aria-label={cell.epochs.map((epoch) => `Run ${epoch.epoch}: ${epoch.status}`).join(", ")}>
            {cell.epochs.map((epoch) => <span key={epoch.epoch} className={`run-dot ${epoch.status}`} />)}</span>
          <span className="heat-chip" data-empty={cell.score === null} style={heat(cell.score)}>{cell.passed}/{cell.total}</span>
        </button>;
      })}
      {table.pillars[value].cells[key].state === "empty" && <p className="muted">No evals yet for this mode.</p>}
    </section>)}</div>;
}

function EvalView({ evaluation, epochs }: { evaluation: Eval; epochs: Epoch[] }) {
  const [expanded, setExpanded] = useState<number[]>(() => {
    const failed = epochs.find((epoch) => epoch.status === "failed");
    return failed ? [failed.epoch] : [];
  });
  return <>
    <p className="why">{evaluation.motivation}</p>
    <details className="prompt-disclosure"><summary>Prompt</summary><pre>{evaluation.prompt}</pre>
      {evaluation.choices.length > 0 && <ol className="prompt-choices" type="A">{evaluation.choices.map((choice, index) => <li key={index}>{choice}</li>)}</ol>}
    </details>
    <section className="detail-section"><h3>Runs</h3>{epochs.map((epoch) =>
      <details className="run-row" key={epoch.epoch} open={expanded.includes(epoch.epoch)}>
        <summary onClick={(event) => { event.preventDefault(); setExpanded((values) => values.includes(epoch.epoch)
          ? values.filter((value) => value !== epoch.epoch) : [...values, epoch.epoch]); }}>
          <span>Run {epoch.epoch}</span><Verdict epoch={epoch} /><span>{money(epoch.cost, 4)}</span>
          <span>{epoch.total_seconds === null ? "–" : `${epoch.total_seconds.toFixed(1)}s`}</span><span>{epoch.total_tokens.toLocaleString("en")} tokens</span>
        </summary>
        <div className="run-details">
          {epoch.issue && <p className="issue">{epoch.error_kind ?? epoch.limit?.type ?? "Run"}: {epoch.issue}</p>}
          {epoch.status === "error" && <p className="caution">This error does not enter the score.</p>}
          {epoch.limit && <p className="caution">{epoch.limit.type} limit: {epoch.limit.limit}{epoch.limit.reason ? ` · ${epoch.limit.reason}` : ""}</p>}
          <ul className="checks">{Object.entries(epoch.checks).sort((a, b) => Number(a[1].passed) - Number(b[1].passed)).map(([name, check]) =>
            <li key={name}><span className={check.passed ? "positive" : "negative"}>{check.passed ? <Check size={16} /> : <X size={16} />}</span>
              <div><code>{name}</code><p>{check.reason}</p></div></li>)}</ul>
          {!Object.keys(epoch.checks).length && <p className="muted">No checks completed.</p>}
          <p className="muted">Model: {money(epoch.model_cost_usd, 4)} · Grader: {money(epoch.grader_cost_usd, 4)} · Cost source: {epoch.cost_source}. Time includes setup. Tokens include the model and grader.</p>
          {epoch.logHref || epoch.logUrl ? <div className="log-links"><a className="button" href={epoch.logHref ?? epoch.logUrl!} target="_blank" rel="noreferrer">Open log ↗</a>
            {epoch.logHref && epoch.logUrl && epoch.logHref !== epoch.logUrl && <a href={epoch.logUrl} target="_blank" rel="noreferrer">Download log ↗</a>}</div> : <p className="muted">Full log not published.</p>}
        </div>
      </details>)}
      {!epochs.length && <p>No epochs yet.</p>}
    </section>
  </>;
}

export function Detail({ selection, data, onSelect }: {
  selection: Selection; data: BoardData; onSelect: (selection: Selection) => void;
}) {
  const { evaluation, pillar, agent, mode, fromList } = selection;
  const table = data.tables[mode], key = agentKey(agent), summary = table.summaries[key];
  const cell = evaluation ? table.pillars[evaluation.pillar].evals.find((entry) => entry.id === evaluation.id)?.cells[key] : undefined;
  const scope = pillar ? table.pillars[pillar].cells[key] : summary;
  return <div className="detail-body">
    <header className="drawer-header"><h1>{evaluation?.title ?? (pillar ? names[pillar] : "All pillars")}</h1>
      <Configuration agent={agent} /><p className="muted">{modeNames[mode]}</p>
      {!evaluation && <p>{percent(summary.scores[pillar ?? "overall"])} · {scope.passed}/{scope.total} scored · {scope.errors} errors excluded</p>}
      {!evaluation && summary.scores[pillar ?? "overall"] === null && <p className="muted">{pillar && table.pillars[pillar].cells[key].state === "empty" ? "No evals yet" : "No epochs yet"}</p>}
    </header>
    {evaluation && fromList && <button className="back-button" onClick={() => onSelect({ agent, mode, pillar })}>
      <ArrowLeft size={14} />{pillar ? names[pillar] : "All pillars"}</button>}
    {evaluation ? <EvalView key={evaluation.id} evaluation={evaluation} epochs={cell?.epochs ?? []} /> :
      <EvalList table={table} evaluations={data.evaluations} agent={agent} pillar={pillar}
        onEval={(value) => onSelect({ ...selection, evaluation: value, fromList: true })} />}
  </div>;
}

export default function Board({ data }: { data: BoardData }) {
  const query = useQuery();
  const mode: Mode = query.get("mode") === "skills" ? "skills" : query.get("mode") === "vanilla" ? "vanilla" : "internet";
  const [sort, setSort] = useState<{ key: Sort; ascending: boolean }>({ key: "overall", ascending: false });
  const pushed = useRef(false);
  const opener = useRef<HTMLElement | null>(null);
  const selection = decodeSelection(query, data);
  useEffect(() => { if (!selection) opener.current?.focus({ preventScroll: true }); }, [selection]);
  const table = data.tables[mode];
  const changeMode = (value: Mode) => updateQuery({ mode: value });
  const select = (value: Selection) => {
    if (!selection) { pushed.current = true; opener.current = document.activeElement as HTMLElement | null; }
    updateQuery({ d: JSON.stringify({ agent: agentKey(value.agent),
      mode: value.mode, pillar: value.pillar, eval: value.evaluation?.id, list: value.fromList }) }, !selection);
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
  const matrixAgents = [...table.agents].sort((a, b) =>
    (data.tables[mode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(b)].scores.overall ?? -1) -
    (data.tables[mode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(a)].scores.overall ?? -1));
  return <TooltipProvider delayDuration={200}><main id="main" className="page">
    {data.demo && <aside className="banner"><strong>Demo data</strong> · Invented results for a board preview.</aside>}
    <header className="hero"><div className="hero-brand"><h1 id="hero-logo" aria-label="ETH Evals"><Logo id="hero-gradient" /></h1>
      <p className="hero-plate"><span><b>{data.counts.evals}</b> evals</span><span><b>{data.counts.agents}</b> agents</span><span><b>{data.counts.runs.toLocaleString("en")}</b> runs</span></p></div>
      <p className="hero-tag">The Open Benchmark for AI on Ethereum</p>
      <p className="hero-desc">We test AI agents, and the models behind them, on real Ethereum work. Every task, run and transcript is public, and anyone can run the same evals.</p>
      <p className="hero-desc">We evaluate <Link href="/how-it-works/#hw-pillars">four pillars</Link>: <b>Concepts</b>, <b>Transactions</b>, <b>Building</b> and <b>Security</b>.</p>
    </header>
    <section id="leaderboard" className="results-section"><div className="section-head"><div><h2>Results</h2><p>The same work, with and without Ethereum skills.</p></div>
      <Link className="text-link" href={`/compare/?mode=${mode}`}>Compare configurations →</Link></div>
      <div className="toolbar"><ModeToggle mode={mode} onChange={changeMode} />{mode === "vanilla" && <p className="mode-note">Model only calls the API with no tools or web. Its eval set differs from the agent modes.</p>}</div>
      {agents.length ? <div className="table-shell"><div className="table-scroll" role="region" tabIndex={0} aria-label="Leaderboard. Scroll horizontally for all columns.">
        <table className="leaderboard"><caption className="sr-only">Configuration scores, sorted by {sort.key} {sort.ascending ? "ascending" : "descending"}</caption>
          <colgroup><col className="config-col" />{columns.map(([key]) => <col key={key} className="score-col" />)}</colgroup>
          <thead><tr><th scope="col" className="row-label">{mode === "vanilla" ? "Model" : "Configuration"}<small>model · harness</small></th>
            {columns.map(([key, name]) => <th key={key} scope="col" aria-sort={sort.key === key ? sort.ascending ? "ascending" : "descending" : "none"}>
              <button className="sort-button" onClick={() => setSort({ key, ascending: sort.key === key ? !sort.ascending : key === "costPerPass" })}>{name}{sort.key === key && (sort.ascending ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
            </th>)}</tr></thead><tbody>{agents.map((agent) => <tr key={agentKey(agent)}><th scope="row" className="row-label"><Configuration agent={agent} /></th>
              {columns.map(([key]) => <td key={key}>{key === "costPerPass" ? <Hint text={formulas.cost}><span className="cost-value">{money(value(agent, key))}</span></Hint> :
                <Score score={value(agent, key)} lift={mode === "skills" ? data.lifts[agentKey(agent)]?.[key] : undefined}
                  formula={key === "overall" ? formulas.overall : formulas.pillar}
                  label={`${key === "overall" ? "Overall" : names[key]}, ${agentLabel(agent)}`}
                  empty={key !== "overall" && table.pillars[key].cells[agentKey(agent)].state === "empty" ? "No evals yet" : "No epochs yet"}
                  onOpen={() => select({ agent, mode, pillar: key === "overall" ? undefined : key })} />}</td>)}
            </tr>)}</tbody></table></div><div className="table-note">Click a score for its evals and runs.{mode === "skills" && " +pp is the change over Internet."} Costs are in USD.</div></div> :
        <div className="empty"><h3>{mode === "vanilla" ? "No model epochs yet" : "No agent epochs yet"}</h3><p>No published results match the current evals. Browse the eval catalog below.</p></div>}
      <div className="read-note" id="scoring"><b>How to read it.</b> An epoch passes only if every check passes. An eval score is its pass rate. A pillar score is the mean of its scored evals, and Overall is the mean of scored pillars. Errors stay visible in the details and do not enter scores. Cost limits count as failures. An epoch that reaches its time limit is graded on the work it left. Counts show the scored epochs; no confidence intervals are shown.</div>
    </section>
    <section id="evals" className="results-section"><div className="section-head"><div><h2>Results by eval · {modeNames[mode]}</h2><p>The scores above, broken down: how many runs each agent passed on every eval, grouped by pillar.</p></div>
      <a className="button" href={`${repo}/blob/main/docs/add-an-eval.md`} target="_blank" rel="noreferrer">How to add an eval ↗</a></div>
      <p className="eyebrow">{pillars.reduce((sum, pillar) => sum + table.pillars[pillar].evals.length, 0)} evals · {modeNames[mode]}</p>
      <div className="table-shell"><div className="matrix-title">Eval matrix · {modeNames[mode]}</div><div className="table-scroll matrix-scroll" role="region" tabIndex={0} aria-label="Eval matrix. Scroll for more configurations.">
        <table className="matrix"><caption className="sr-only">Passed runs / scored runs for each eval and configuration</caption><thead><tr><th className="row-label" scope="col">Eval</th>
          {matrixAgents.map((agent) => <th key={agentKey(agent)} scope="col"><Configuration agent={agent} /></th>)}</tr></thead>
          <tbody>{pillars.map((pillar) => <Fragment key={pillar}><tr className="pillar-band"><th scope="colgroup" colSpan={matrixAgents.length + 1}>{names[pillar]}<small>{table.pillars[pillar].evals.length} evals</small></th></tr>
            {table.pillars[pillar].evals.length ? table.pillars[pillar].evals.map((entry) => <tr key={entry.id} id={`eval-${entry.id.replaceAll("/", "-")}`}>
              <th scope="row" className="row-label"><span className="eval-title">{data.evaluations[entry.id].title}</span><small>{entry.id}</small></th>
              {matrixAgents.map((agent) => { const cell = entry.cells[agentKey(agent)];
                return <td key={agentKey(agent)}>{cell.state === "na" || cell.score === null ?
                  <span className="matrix-cell" data-empty title={cell.state === "na" ? "Not applicable" : cell.errors ? `${cell.errors} errors; no scored epochs` : "No epochs yet"}>–</span> :
                  <Hint text={formulas.eval}><button className="matrix-cell" style={heat(cell.score)}
                    aria-label={`${data.evaluations[entry.id].title}, ${modelLabel(agent.model)}: ${cell.passed} of ${cell.total} epochs passed. Open details.`}
                    onClick={() => select({ evaluation: data.evaluations[entry.id], agent, mode })}>{cell.passed}/{cell.total}</button></Hint>}</td>;
              })}
            </tr>) : <tr><td colSpan={matrixAgents.length + 1} className="no-evals">No evals yet</td></tr>}
          </Fragment>)}</tbody></table></div><div className="table-note">Runs passed per eval. Click a scored cell for its prompt and runs. Errors are excluded from counts.</div></div>
    </section>
    <noscript>Enable JavaScript to change modes and open run details.</noscript>
  </main>
    <Sheet open={selection !== null} onOpenChange={(open) => { if (!open) close(); }}>
      {selection && <SheetContent>
        <SheetTitle className="sr-only">Eval and run details</SheetTitle><SheetDescription className="sr-only">Scores, prompts, checks, costs and logs.</SheetDescription>
        <Detail selection={selection} data={data} onSelect={select} /></SheetContent>}
    </Sheet>
  </TooltipProvider>;
}
