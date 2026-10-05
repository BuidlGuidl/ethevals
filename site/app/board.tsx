"use client";

import { Fragment, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowDown, ArrowUp, Check, X, AlertTriangle } from "lucide-react";
import { agentDetails, harnessLabel, modelLabel } from "../src/labels";
import { pillars, agentKey, type BoardData, type DisplayEval as Eval, type Mode, type Pillar, type Epoch, type Agent } from "../src/board";
import { Logo } from "../components/logo";
import { ModeToggle, modeNames } from "../components/mode-toggle";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { TooltipProvider } from "../components/ui/tooltip";
import { Score, Hint, formulas, heat, percent, money } from "../components/scores";
import { updateQuery, useQuery } from "../components/url-state";
import { repo } from "../components/shell";

export const names: Record<Pillar, string> = { concepts: "Concepts", transactions: "Transactions", building: "Building", security: "Security" };
export type Selection = { evaluation?: Eval; pillar?: Pillar; agent?: Agent; mode: Mode; run?: number };
type Sort = "overall" | Pillar | "costPerPass";

export function Configuration({ agent }: { agent: Agent }) {
  return <span title={agentDetails(agent)} className="configuration"><b>{modelLabel(agent.model)}</b>
    <small>{agent.harness ? harnessLabel(agent.harness) : "API call · no tools"} · effort {agent.effort ?? "provider default"}</small></span>;
}

function Prompt({ evaluation }: { evaluation: Eval }) {
  return <div className="prompt"><pre>{evaluation.prompt}</pre>{evaluation.choices.length > 0 &&
    <ol type="A">{evaluation.choices.map((choice, index) => <li key={index}>{choice}</li>)}</ol>}</div>;
}

function Verdict({ epoch }: { epoch: Epoch }) {
  return <span className={`verdict ${epoch.status === "passed" ? "positive" : epoch.status === "failed" ? "negative" : "caution"}`}>
    {epoch.status === "passed" ? <Check size={14} /> : epoch.status === "failed" ? <X size={14} /> : <AlertTriangle size={14} />}
    {epoch.status === "passed" ? "Pass" : epoch.status === "failed" ? "Fail" : "Error"}</span>;
}

function RunDots({ epochs, onRun }: { epochs: Epoch[]; onRun: (epoch: Epoch) => void }) {
  return <span className="run-dots">{epochs.map((epoch) => <Hint key={epoch.epoch} text={`Run ${epoch.epoch}: ${epoch.status}`}>
    <button className={`run-dot ${epoch.status}`} aria-label={`Open run ${epoch.epoch}, ${epoch.status}`} onClick={() => onRun(epoch)} />
  </Hint>)}</span>;
}

export function Detail({ selection, data, onSelect }: {
  selection: Selection; data: BoardData; onSelect: (selection: Selection) => void; onClose: () => void;
}) {
  const { evaluation, pillar, agent, mode, run } = selection;
  const table = data.tables[mode];
  const agents = agent ? [agent] : table.agents;
  const entries = pillars.filter((value) => !pillar || pillar === value).flatMap((value) => table.pillars[value].evals)
    .filter((entry) => data.evaluations[entry.id].modes.includes(mode));
  const evalEntry = evaluation ? table.pillars[evaluation.pillar].evals.find((entry) => entry.id === evaluation.id) : undefined;
  const cell = agent ? evalEntry?.cells[agentKey(agent)] : undefined;
  const epochs = cell?.epochs ?? [];
  const epoch = epochs.find((entry) => entry.epoch === run);
  const summary = agent ? table.summaries[agentKey(agent)] : undefined;
  const scopeCell = agent && pillar ? table.pillars[pillar].cells[agentKey(agent)] : undefined;
  const title = epoch ? `Run ${epoch.epoch}` : evaluation?.title ?? (pillar ? names[pillar] : "All pillars");
  const score = cell ? cell.score : scopeCell ? scopeCell.score : evaluation ? null : summary?.overall ?? null;
  const empty = scopeCell?.state === "empty" ? "No evals yet" : "No epochs yet";
  const openRun = (value: Epoch, chosen = agent) => onSelect({ ...selection, agent: chosen, run: value.epoch });
  const matchingAgent = (value: Mode) => agent && data.tables[value].agents.find((candidate) =>
    agentKey(candidate) === agentKey(agent) || ((value === "vanilla" || mode === "vanilla") && candidate.model === agent.model && candidate.effort === agent.effort));
  const disabledModes = (["internet", "skills", "vanilla"] as Mode[]).filter((value) =>
    (evaluation && !evaluation.modes.includes(value)) || (agent && !matchingAgent(value)));
  return <div className="detail-body">
    <header className="drawer-header"><p className="eyebrow">{modeNames[mode]}{agent ? ` · ${modelLabel(agent.model)} · ${agent.harness ? harnessLabel(agent.harness) : "API"}` : ""}</p>
      <h1 id="detail-title">{title}</h1><p className="muted">{evaluation?.id ?? (agent ? agentDetails(agent) : "Eval details")}</p>
    </header>
    {(evaluation || run) && <button className="back-button" onClick={() => onSelect(run ? { ...selection, run: undefined } : { ...selection, evaluation: undefined })}>
      <ArrowLeft size={14} />{run ? "All runs" : "All evals"}</button>}
    <ModeToggle mode={mode} disabled={disabledModes} onChange={(value) => onSelect({ ...selection, mode: value, run: undefined,
      agent: matchingAgent(value) })} label="Detail mode" />
    {epoch ? <>
      <div className="run-strip">{epochs.map((value) => <button key={value.epoch} aria-pressed={value.epoch === epoch.epoch} onClick={() => openRun(value)}>Run {value.epoch}</button>)}</div>
      <section className="detail-section"><Verdict epoch={epoch} /><p>A run passes only if every check passes.</p>
        {epoch.issue && <p className="issue">{epoch.error_kind ?? epoch.limit?.type ?? "Run"}: {epoch.issue}</p>}
        {epoch.status === "error" && <p className="caution">This error does not enter the score.</p>}
        {epoch.limit && <p className="caution">{epoch.limit.type} limit: {epoch.limit.limit}{epoch.limit.reason ? ` · ${epoch.limit.reason}` : ""}</p>}
      </section>
      <section className="detail-section"><h3>Checks</h3><Checks epochs={[epoch]} reasons /></section>
      <div className="summary-tiles"><div><small>Model cost</small><b>{money(epoch.model_cost_usd, 4)}</b></div>
        <div><small>Grader cost</small><b>{money(epoch.grader_cost_usd, 4)}</b></div>
        <div><small>Time</small><b>{epoch.total_seconds === null ? "–" : `${epoch.total_seconds.toFixed(1)}s`}</b></div>
        <div><small>Total tokens</small><b>{epoch.total_tokens.toLocaleString("en")}</b></div></div>
      <p className="muted">Cost source: {epoch.cost_source}. Time includes setup. Tokens include the model and grader.</p>
      {epoch.logHref || epoch.logUrl ? <div className="log-links"><a className="button" href={epoch.logHref ?? epoch.logUrl!} target="_blank" rel="noreferrer">Open log ↗</a>
        {epoch.logHref && epoch.logUrl && epoch.logHref !== epoch.logUrl && <a href={epoch.logUrl} target="_blank" rel="noreferrer">Download log ↗</a>}</div> : <p className="muted">Full log not published.</p>}
    </> : evaluation ? <>
      <div className="heat-chip" style={heat(cell?.score ?? null)}>{percent(cell?.score ?? null)}{cell && <small>{cell.passed}/{cell.total} scored · {cell.errors} errors excluded</small>}</div>
      <section className="detail-section"><h3>Motivation</h3><p className="why">{evaluation.motivation}</p></section>
      <section className="detail-section"><h3>Prompt</h3><Prompt evaluation={evaluation} /></section>
      <section className="detail-section"><h3>Checks</h3><Checks epochs={agents.flatMap((item) => evalEntry?.cells[agentKey(item)]?.epochs ?? [])} />
        <p className="muted">A run passes only if every check passes.</p></section>
      <section className="detail-section"><h3>Runs</h3>{!evaluation.modes.includes(mode) ? <p>Not applicable</p> : <>
        <div className="table-scroll"><table className="runs-table"><caption className="sr-only">Runs for {evaluation.title}</caption>
          <thead><tr>{["Configuration", "Run", "Verdict", "Cost", "Time", "Tokens"].map((label) => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>{agents.flatMap((item) => (evalEntry?.cells[agentKey(item)]?.epochs ?? []).map((value) => <tr key={`${agentKey(item)}-${value.epoch}`}>
            <th><Configuration agent={item} /></th><td><button className="text-link" onClick={() => openRun(value, item)}>Run {value.epoch} →</button></td><td><Verdict epoch={value} /></td>
            <td>{money(value.cost, 4)}</td><td>{value.total_seconds === null ? "–" : `${value.total_seconds.toFixed(1)}s`}</td><td>{value.total_tokens.toLocaleString("en")}</td>
          </tr>))}</tbody></table></div>
        {!agents.some((item) => evalEntry?.cells[agentKey(item)]?.epochs.length) && <p>No epochs yet.</p>}
      </>}</section>
    </> : <>
      <div className="summary-tiles"><div><small>{pillar ? "Pillar score" : "Overall"}</small><b>{percent(score)}</b></div>
        <div><small>Passed / scored</small><b>{scopeCell?.passed ?? summary?.passed ?? 0}/{scopeCell?.total ?? summary?.total ?? 0}</b></div>
        <div><small>Errors excluded</small><b>{scopeCell?.errors ?? summary?.errors ?? 0}</b></div>
        <div><small>$ / pass · all pillars</small><b>{money(summary?.costPerPass ?? null)}</b></div></div>
      {score === null && <p className="mono">{empty}</p>}
      <div className="eval-list">{entries.map((entry) => {
        const ev = data.evaluations[entry.id], value = agent ? entry.cells[agentKey(agent)] : undefined;
        return <article key={entry.id}><button className="eval-list-title" onClick={() => onSelect({ ...selection, evaluation: ev })}><b>{ev.title}</b><small>{ev.id}</small></button>
          {value && <><RunDots epochs={value.epochs} onRun={(epoch) => onSelect({ ...selection, evaluation: ev, run: epoch.epoch })} />
            <button className="heat-chip" style={heat(value.score)} onClick={() => onSelect({ ...selection, evaluation: ev })}>{percent(value.score)}<small>{value.passed}/{value.total}</small></button></>}
        </article>;
      })}</div>{!entries.length && <p>No evals yet for this mode.</p>}
    </>}
  </div>;
}

function Checks({ epochs, reasons = false }: { epochs: Epoch[]; reasons?: boolean }) {
  const checks = Object.fromEntries(epochs.flatMap((epoch) => Object.entries(epoch.checks)));
  return Object.keys(checks).length ? <ul className="checks">{Object.entries(checks).map(([name, check]) => <li key={name}>
    {reasons && <span className={check.passed ? "positive" : "negative"}>{check.passed ? <Check size={16} /> : <X size={16} />}</span>}
    <div><code>{name}</code>{reasons && <p>{check.reason}</p>}</div></li>)}</ul> : <p className="muted">{reasons ? "No checks completed." : "Check names appear after the first run."}</p>;
}

function decodeSelection(query: URLSearchParams, data: BoardData): Selection | null {
  const raw = query.get("d");
  if (!raw) {
    const ev = data.evaluations[query.get("eval") ?? ""];
    return ev ? { evaluation: ev, mode: "internet" } : null;
  }
  try {
    const value = JSON.parse(raw);
    if (!["internet", "skills", "vanilla"].includes(value.mode)) return null;
    const agent = data.tables[value.mode as Mode].agents.find((item) => agentKey(item) === value.agent);
    if (value.agent && !agent) return null;
    return { agent, mode: value.mode, evaluation: data.evaluations[value.eval],
      pillar: pillars.includes(value.pillar) ? value.pillar : undefined,
      run: Number.isInteger(value.run) && value.run > 0 ? value.run : undefined };
  } catch { return null; }
}

export default function Board({ data }: { data: BoardData }) {
  const query = useQuery();
  const mode: Mode = query.get("mode") === "skills" ? "skills" : query.get("mode") === "vanilla" ? "vanilla" : "internet";
  const [sort, setSort] = useState<{ key: Sort; ascending: boolean }>({ key: "overall", ascending: false });
  const pushed = useRef(false);
  const opener = useRef<HTMLElement | null>(null);
  const selection = decodeSelection(query, data);
  const table = data.tables[mode];
  const changeMode = (value: Mode) => updateQuery({ mode: value });
  const select = (value: Selection) => {
    if (!selection) { pushed.current = true; opener.current = document.activeElement as HTMLElement | null; }
    updateQuery({ eval: null, d: JSON.stringify({ agent: value.agent ? agentKey(value.agent) : undefined,
      mode: value.mode, pillar: value.pillar, eval: value.evaluation?.id, run: value.run }) }, !selection);
  };
  const close = () => {
    if (pushed.current) { pushed.current = false; window.history.back(); }
    else updateQuery({ d: null, eval: null });
  };
  const value = (agent: Agent, key: Sort) => key === "overall" || key === "costPerPass"
    ? table.summaries[agentKey(agent)][key] : table.pillars[key].cells[agentKey(agent)].score;
  const agents = [...table.agents].sort((a, b) => {
    const x = value(a, sort.key), y = value(b, sort.key);
    return x === null ? y === null ? agentKey(a).localeCompare(agentKey(b)) : 1 : y === null ? -1 : (sort.ascending ? 1 : -1) * (x - y) || agentKey(a).localeCompare(agentKey(b));
  });
  const columns: [Sort, string][] = [["overall", "Overall"], ...pillars.map((pillar): [Sort, string] => [pillar, names[pillar]]), ["costPerPass", "$ / pass"]];
  const matrixAgents = [...table.agents].sort((a, b) =>
    (data.tables[mode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(b)].overall ?? -1) -
    (data.tables[mode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(a)].overall ?? -1));
  return <TooltipProvider delayDuration={200}><main id="main" className="page results-page">
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
              {columns.map(([key]) => <td key={key}>{key === "costPerPass" ? <Hint text={formulas.cost}><span tabIndex={0} className="cost-value">{money(value(agent, key))}</span></Hint> :
                <Score score={value(agent, key)} lift={mode === "skills" ? data.lifts[agentKey(agent)]?.[key] : undefined}
                  formula={key === "overall" ? formulas.overall : formulas.pillar}
                  label={`${key === "overall" ? "Overall" : names[key]}, ${agent.harness ? `${harnessLabel(agent.harness)} / ` : ""}${modelLabel(agent.model)}`}
                  empty={key !== "overall" && table.pillars[key].cells[agentKey(agent)].state === "empty" ? "No evals yet" : "No epochs yet"}
                  onOpen={() => select({ agent, mode, pillar: key === "overall" ? undefined : key })} />}</td>)}
            </tr>)}</tbody></table></div><div className="table-note">Click a score for its evals and runs.{mode === "skills" && " +pp is the change over Internet."} Costs are in USD.</div></div> :
        <div className="empty"><h3>{mode === "vanilla" ? "No model epochs yet" : "No agent epochs yet"}</h3><p>No published results match the current evals. Browse the eval catalog below.</p></div>}
      <div className="read-note" id="scoring"><b>How to read it.</b> An epoch passes only if every check passes. An eval score is its pass rate. A pillar score is the mean of its scored evals, and Overall is the mean of scored pillars. Errors stay visible in the details and do not enter scores. Cost limits count as failures. An epoch that reaches its time limit is graded on the work it left. Counts show the scored epochs; no confidence intervals are shown.</div>
    </section>
    <section id="evals" className="results-section"><div className="section-head"><div><h2>Results by eval</h2><p>The scores above, broken down: how many runs each agent passed on every eval, grouped by pillar.</p></div>
      <a className="button" href={`${repo}/blob/main/docs/add-an-eval.md`} target="_blank" rel="noreferrer">How to add an eval ↗</a></div>
      <ModeToggle mode={mode} onChange={changeMode} /><p className="eyebrow">{pillars.reduce((sum, pillar) => sum + table.pillars[pillar].evals.length, 0)} evals · {modeNames[mode]}</p>
      <div className="table-shell"><div className="matrix-title">Eval matrix · {modeNames[mode]}</div><div className="table-scroll matrix-scroll" role="region" tabIndex={0} aria-label="Eval matrix. Scroll for more configurations.">
        <table className="matrix"><caption className="sr-only">Passed runs / scored runs for each eval and configuration</caption><thead><tr><th className="row-label" scope="col">Eval</th>
          {matrixAgents.map((agent) => <th key={agentKey(agent)} scope="col"><Configuration agent={agent} /></th>)}</tr></thead>
          <tbody>{pillars.map((pillar) => <Fragment key={pillar}><tr className="pillar-band"><th scope="colgroup" colSpan={matrixAgents.length + 1}>{names[pillar]}<small>{table.pillars[pillar].evals.length} evals</small></th></tr>
            {table.pillars[pillar].evals.length ? table.pillars[pillar].evals.map((entry) => <tr key={entry.id}>
              <th scope="row" className="row-label"><button className="eval-title" onClick={() => select({ evaluation: data.evaluations[entry.id], mode })}>{data.evaluations[entry.id].title}</button><small>{entry.id}</small></th>
              {matrixAgents.map((agent) => { const cell = entry.cells[agentKey(agent)]; return <td key={agentKey(agent)}><Hint text={formulas.eval}><button className="matrix-cell" style={heat(cell.score)}
                aria-label={`${data.evaluations[entry.id].title}, ${modelLabel(agent.model)}: ${cell.state === "na" ? "Not applicable" : `${cell.passed} of ${cell.total} epochs passed`}. Open details.`}
                onClick={() => select({ evaluation: data.evaluations[entry.id], agent, mode })}>{cell.state === "na" ? "–" : cell.score === null ? "no run" : `${cell.passed}/${cell.total}`}</button></Hint></td>; })}
            </tr>) : <tr><td colSpan={matrixAgents.length + 1} className="no-evals">No evals yet</td></tr>}
          </Fragment>)}</tbody></table></div><div className="table-note">Runs passed per eval. Click an eval for its prompt, or a cell for its runs. Errors are excluded from counts.</div></div>
    </section>
    <noscript>Enable JavaScript to change modes and open run details.</noscript>
  </main>
    <Sheet open={selection !== null} onOpenChange={(open) => { if (!open) close(); }}>
      {selection && <SheetContent onCloseAutoFocus={(event) => { event.preventDefault(); opener.current?.focus({ preventScroll: true }); }}>
        <SheetTitle className="sr-only">Eval and run details</SheetTitle><SheetDescription className="sr-only">Scores, prompts, checks, costs and logs.</SheetDescription>
        <Detail selection={selection} data={data} onSelect={select} onClose={close} /></SheetContent>}
    </Sheet>
  </TooltipProvider>;
}
