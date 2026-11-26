"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowDown, ArrowUp, Check, X, AlertTriangle, ShieldBan } from "lucide-react";
import { agentLabel, modeHints, names, modeNames, unwrapPrompt } from "../src/labels";
import { pillars, agentKey, scoreSummary, weightedOverall, pillarTaskCap, emptyTrialLabel, type BoardData, type Table, type DisplayEval as Eval, type Pillar, type Mode, type Trial, type Agent } from "../src/board";
import { domains, domainNames, type Domain } from "../src/areas";
import { DomainFilter, selectDomain } from "../components/domain-filter";
import { decodeSelection, encodeSelection, type Selection } from "../src/selection";
import { Configuration } from "../components/configuration";
import { Logo } from "../components/logo";
import { ModeToggle } from "../components/mode-toggle";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { TooltipProvider } from "../components/ui/tooltip";
import { Score, Hint, InfoHint, CornerMarks, unscored, peers, tile, percent, money, tokens } from "../components/scores";
import { entryLabels, notRunTrials, TrialDot, TrialDots, TrialLegend, taskHint, trialHint, trialNote, trialScoreText, trialState } from "../components/trial-display";
import { ignoringRefusals, updateQuery, useQuery } from "../components/url-state";
import { drawerRefusalBanner, ignoreRefusals, ignoresRefusals, isRefusedTrial, refusalLines, refusals, refusalStrip, refusedCount, retryRefusals, sentences, tableHasRefusals, taskRefusalLines } from "../src/refusals";
import { RefusalStrip, RefusalSwitch } from "../components/refusal-controls";
import { repo } from "../src/repo";
import { readMode } from "../src/modes";
import { checkKind } from "../src/scoring";

type Sort = "overall" | Pillar;

const duration = (trial: Trial) => trial.total_seconds === null ? "–" : `${trial.total_seconds.toFixed(1)}s`;

function EvalList({ table, evaluations, agent, pillar, domain, onEval }: {
  table: Table; evaluations: BoardData["evaluations"]; agent: Agent; pillar?: Pillar; domain?: Domain; onEval: (evaluation: Eval) => void;
}) {
  const key = agentKey(agent);
  const groups = pillars.filter((value) => !pillar || pillar === value).map((value) => ({
    value, entries: table.pillars[value].evals.filter((entry) => entry.cells[key].state !== "na"
      && (!domain || evaluations[entry.id].domain === domain)),
  }));
  const refused = groups.some(({ entries }) => refusedCount(entries.map((entry) => entry.cells[key])) > 0);
  return <div className="eval-list"><TrialLegend refused={refused} />{groups.filter(({ entries }) => !domain || entries.length).map(({ value, entries }) =>
    <section key={value} className={`pillar-${value}`}>{!pillar && <h3>{names[value]}</h3>}
      {entries.map((entry) => {
        const evaluation = evaluations[entry.id], cell = entry.cells[key];
        const row = peers(table.agents.map((other) => entry.cells[agentKey(other)].score)), chip = tile(cell.score, row);
        return <button key={entry.id} className="eval-list-row" onClick={() => onEval(evaluation)}>
          <span className="eval-list-title"><b>{evaluation.title}</b><small>{evaluation.id}</small></span>
          <span className="eval-list-result">{cell.cost !== null && <span className="task-cost">{money(cell.cost)} · {tokens(cell.tokens)} tok</span>}{cell.trials.length > 0 && <TrialDots trials={cell.trials} />}
          <span className="heat-chip" {...chip} title={cell.score === null ? emptyLabel(cell) : undefined}><span>{percent(cell.score)}</span>
            {cell.score !== null && row.top !== null && <small className="heat-best">{chip["data-tone"] === "leader" ? "best" : `best ${row.top}%`}</small>}</span></span>
        </button>;
      })}
      {table.pillars[value].cells[key].state === "empty" && <p className="muted">No tasks yet for this mode.</p>}
    </section>)}{domain && !groups.some(({ entries }) => entries.length) && <p className="muted">No tasks yet for this domain and mode.</p>}</div>;
}

function EvalView({ evaluation, trials, notRun, onRun }: { evaluation: Eval; trials: Trial[]; notRun: number[]; onRun: (run: number) => void }) {
  // Saved trials and planned trials that never ran, in trial order.
  const rows = [...trials.map((trial) => ({ trial: trial.trial, saved: trial })), ...notRun.map((trial) => ({ trial, saved: undefined }))]
    .sort((a, b) => a.trial - b.trial);
  return <>
    <p>{evaluation.description}</p>
    <details className="prompt-disclosure" open><summary>Instruction</summary><pre>{unwrapPrompt(evaluation.instruction)}</pre>
    </details>
    <section className="detail-section"><h3>Trials</h3>{rows.length ?
      <div className="table-shell"><div className="table-scroll" role="region" tabIndex={0} aria-label="Trials. Scroll horizontally for all columns.">
        <table className="runs-table"><caption className="sr-only">Trials for this task and configuration. Open a row for checks and trajectories.</caption>
          <thead><tr>{["Trial", "Trial score", "Checks", "Time", "Tokens", "Cost"].map((label) => <th scope="col" key={label}>{label}</th>)}<th scope="col"><span className="sr-only">Open trial</span></th></tr></thead>
          <tbody>{rows.map(({ trial: number, saved: trial }) => !trial ? <tr key={number} className="not-run">
            <td>Trial {number}</td><td>Not run yet</td>{[0, 1, 2, 3].map((index) => <td key={index}>–</td>)}<td aria-hidden="true" /></tr>
            : <tr key={trial.trial}><td><button className="run-open" onClick={() => onRun(trial.trial)}
            aria-label={`${trialHint(trial)}. Open trial.`}>Trial {trial.trial}</button></td>
            <td><span className="trial-score"><TrialDot state={trialState(trial)} ignored={trial.ignored} />{trialScoreText(trial)}</span></td>
            <td className={isRefusedTrial(trial) ? "refusal-text" : trial.score.value !== null && trial.score.stop ? "negative" : undefined}>{trial.score.value === null ? "–" : trialNote(trial)}</td>
            <td>{duration(trial)}</td><td>{tokens(trial.total_tokens)}</td><td>{money(trial.cost)}</td><td aria-hidden="true">›</td></tr>)}</tbody></table>
      </div></div> : <p>No trials yet.</p>}
    </section>
  </>;
}

type Checks = [string, Trial["checks"][string]][];

function CheckList({ checks }: { checks: Checks }) {
  return <ul className="checks">{checks.map(([name, check]) => <li key={name}>
    <span className={check.passed ? "positive" : "negative"}>
      {check.passed ? <Check size={16} aria-label="Passed" /> : <X size={16} aria-label="Failed" />}
    </span><div><code>{name}</code><p>{check.reason}</p></div>
  </li>)}</ul>;
}

const checkNotes = {
  gate: "Did the agent do what the instruction asked for? Any failure sets the trial score to 0%.",
  judgment: "Did the agent make sound Ethereum decisions beyond the instruction? Each check counts toward the trial score.",
  notCounted: "From an older version of this task's checks. It does not count toward the trial score.",
};

function CheckGroup({ label, note, checks }: { label: string; note?: string; checks: Checks }) {
  const failed = checks.filter(([, check]) => !check.passed);
  const passed = checks.filter(([, check]) => check.passed);
  return <section className="check-group">
    <h3>{label} <span>{passed.length} of {checks.length}{note && <InfoHint label={label} text={note} />}</span></h3>
    <CheckList checks={[...failed, ...passed]} />
  </section>;
}

function RunView({ evaluation, trial, trials, onRun }: { evaluation: Eval; trial: Trial; trials: Trial[]; onRun: (run: number) => void }) {
  const checks = Object.entries(trial.checks);
  // A refused trial's refusal note already says it gave no answer.
  const failedEntries = checks.filter(([name, check]) => !check.passed && checkKind(evaluation, name) === "entry"
    && !(name === "no_answer" && isRefusedTrial(trial)));
  const groups = (evaluation.pillar === "concepts"
    ? [{ kind: "concept", label: "Checks", note: undefined }]
    : [{ kind: "gate", label: "Gate checks", note: checkNotes.gate },
      { kind: "judgment", label: "Judgment checks", note: checkNotes.judgment },
      { kind: undefined, label: "Not counted", note: checkNotes.notCounted }])
    .map((group) => ({ ...group, checks: checks.filter(([name]) => checkKind(evaluation, name) === group.kind) }))
    .filter((group) => group.checks.length > 0);
  const { score } = trial;
  return <>
    <div className="run-switcher" role="group" aria-label="Trials">{trials.map((run) => <button key={run.trial}
      aria-pressed={run.trial === trial.trial} aria-label={trialHint(run)} onClick={() => onRun(run.trial)}>
      Trial {run.trial} <TrialDot state={trialState(run)} ignored={run.ignored} /></button>)}</div>
    <dl className="run-stats">{[
      ["Time", duration(trial)],
    ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {score.value === null ? <p className="trial-error">
      <AlertTriangle size={14} aria-hidden="true" />This trial ended in an error, so it is left out of the score.
    </p> : trial.issue && <p className="issue">{trial.error_kind ?? trial.limit?.type ?? "Trial"}: {trial.issue}</p>}
    {isRefusedTrial(trial) ? <p className="refusal-note"><ShieldBan size={14} aria-hidden="true" />{trial.ignored
      ? "Safety refusal on both tries. Left out of the score while refusals are ignored."
      : "Safety refusal on both tries, so this trial scores 0%."}</p>
      : trial.status === "failed" && trial.no_answer?.length === 2 && <p className="negative">Empty reply</p>}
    {retryRefusals(trial) > 0 && <p className="muted">Answered on retry after {retryRefusals(trial)} safety {retryRefusals(trial) === 1 ? "refusal" : "refusals"}.</p>}
    {trial.limit && <p className="caution">{trial.limit.type} limit: {trial.limit.limit}{trial.limit.reason ? ` · ${trial.limit.reason}` : ""}</p>}
    {score.value !== null && <div className="verifier-verdict">
      {failedEntries.map(([name, check]) => <p key={name} className="entry-check"><X size={16} className="negative" aria-hidden="true" />
        <b>{entryLabels[name]}</b><small>{check.reason}</small></p>)}
      {groups.map((group) => <CheckGroup key={`${trial.trial}-${group.kind}`} {...group} />)}
      {!failedEntries.length && !groups.length && !isRefusedTrial(trial) && <p className="muted">No checks counted.</p>}
    </div>}
    <p className="muted">{trial.paid_by === "free" ? "No model spend" : `Paid by ${trial.paid_by === "plan" ? "plan" : "API key"}`} · Cost at API prices</p>
    {trial.trajectoryUrl ? <div className="trajectory-links"><a className="button" href={trial.trajectoryUrl} target="_blank" rel="noreferrer">{trial.trajectoryUrl.startsWith("https://hub.harborframework.com/jobs/") ? "Open full trial on Harbor Hub ↗" : "Open trajectory ↗"}</a></div> : <p className="muted">Trajectory not published.</p>}
  </>;
}

export function Detail({ selection, data, domain, onSelect }: {
  selection: Selection; data: BoardData; domain?: Domain; onSelect: (selection: Selection) => void;
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
  // Banners count trials rolled up out of sight. A task drawer lists each trial in its own row, so it has none.
  const rolledUp = !evaluation;
  const missing = rolledUp ? scope.missing : 0;
  const info = refusals(table, key, pillar ?? "overall");
  const refusalBanner = rolledUp && info.refused ? drawerRefusalBanner(info, ignoresRefusals(table)) : undefined;
  return <TooltipProvider delayDuration={200}><div className="detail-body">
    <header className="drawer-header"><h1 ref={heading} tabIndex={-1} className={trial ? "run-heading" : undefined}>{trial ? <>
      Trial {trial.trial} of {trials.length} <span className="trial-heading-score">{trialScoreText(trial)}</span>
    </> : evaluation?.title ?? (pillar ? names[pillar] : "All pillars")}</h1>
      {trial && <p>{evaluation!.title}</p>}
      <Configuration agent={agent} cost={trial ? trial.cost : evaluation ? cell?.cost ?? null : scope.cost}
        tokens={trial ? trial.total_tokens : evaluation ? cell?.tokens ?? 0 : scope.tokens} plan={summary.plan} /><p className="muted">{modeNames[mode]}</p>
      {missing > 0 && <p className="unscored-banner">{unscored(missing)}</p>}
      {refusalBanner && <p className="refusal-banner"><ShieldBan size={14} aria-hidden="true" />{refusalBanner}</p>}
      {!evaluation && <p>{percent(summary.scores[pillar ?? "overall"])} · {scoredTrials(scope.total)}</p>}
      {!evaluation && summary.scores[pillar ?? "overall"] === null && <p className="muted">{pillar && table.pillars[pillar].cells[key].state === "empty" ? "No tasks yet" : "No trials yet"}</p>}
      {!evaluation && <div className="domain-scores" role="group" aria-label="Filter by domain">
        {domains.map((option) => {
          const cells = pillars.filter((value) => !pillar || value === pillar).map((value) => table.pillars[value].evals
            .filter((entry) => data.evaluations[entry.id].domain === option && entry.cells[key].state !== "na").map((entry) => entry.cells[key]));
          const tasks = cells.flat().length, total = scoreSummary(cells.flat()).total;
          const score = weightedOverall(cells.map((group) => ({ score: scoreSummary(group).score, tasks: group.length })));
          return <button type="button" key={option} aria-pressed={domain === option} disabled={!tasks && domain !== option} onClick={() => selectDomain(domain, option)}>
            <span>{domainNames[option]}</span>
            {!tasks ? <small>No tasks yet</small> : score === null ? <small>No trials yet</small> : <><b>{percent(score)}</b><small>{scoredTrials(total)}</small></>}
          </button>;
        })}
      </div>}
    </header>
    {trial ? <button className="back-button" onClick={() => onSelect({ ...selection, run: undefined })}><ArrowLeft size={14} />All trials</button>
      : evaluation && fromList && <button className="back-button" onClick={() => onSelect({ agent, mode, pillar })}>
        <ArrowLeft size={14} />{pillar ? names[pillar] : "All pillars"}</button>}
    {trial && evaluation ? <RunView evaluation={evaluation} trial={trial} trials={trials} onRun={(run) => onSelect({ ...selection, run })} /> :
      evaluation ? <EvalView evaluation={evaluation} trials={trials} notRun={cell ? notRunTrials(cell) : []} onRun={(run) => onSelect({ ...selection, run })} /> :
      <EvalList table={table} evaluations={data.evaluations} agent={agent} pillar={pillar} domain={domain}
        onEval={(value) => onSelect({ ...selection, evaluation: value, fromList: true })} />}
  </div></TooltipProvider>;
}

const emptyLabel = (cell: Parameters<typeof emptyTrialLabel>[0]) => refusedCount([cell]) ? sentences(taskRefusalLines(cell, true)) : emptyTrialLabel(cell);
const scoredTrials = (count: number) => `${count} scored ${count === 1 ? "trial" : "trials"}`;

export default function Board({ data }: { data: BoardData }) {
  const query = useQuery();
  return <Results data={data} query={query} />;
}

export function Results({ data: base, query }: { data: BoardData; query: URLSearchParams }) {
  const ignored = useMemo(() => ignoreRefusals(base), [base]);
  const ignoring = ignoringRefusals(query);
  const data = ignoring ? ignored : base;
  const mode = readMode(query.get("mode"));
  const evalsMode = readMode(query.get("evals"));
  const domain = domains.find((value) => value === query.get("domain"));
  const [sort, setSort] = useState<{ key: Sort; ascending: boolean }>({ key: "overall", ascending: false });
  const pushed = useRef(false);
  const opener = useRef<HTMLElement | null>(null);
  const selection = decodeSelection(query, data);
  useEffect(() => { if (!selection) opener.current?.focus({ preventScroll: true }); }, [selection]);
  const table = data.tables[mode];
  const matrixTable = data.tables[evalsMode];
  const matrixRows = pillars.map((pillar) => ({ pillar, entries: matrixTable.pillars[pillar].evals
    .filter((entry) => !domain || data.evaluations[entry.id].domain === domain) }));
  const changeMode = (value: Mode) => updateQuery({ mode: value });
  const select = (value: Selection) => {
    if (!selection) { pushed.current = true; opener.current = document.activeElement as HTMLElement | null; }
    updateQuery({ d: encodeSelection(value) }, !selection);
  };
  const close = () => {
    if (pushed.current) { pushed.current = false; window.history.back(); }
    else updateQuery({ d: null });
  };
  const value = (agent: Agent, key: Sort) => table.summaries[agentKey(agent)].scores[key];
  const showRefusals = tableHasRefusals(base.tables[mode]);
  const refusal = (agent: Agent, key: Sort) => {
    const info = refusals(ignored.tables[mode], agentKey(agent), key);
    if (!info.refused) return {};
    if (!ignoring) return { refusal: refusalLines(info, false) };
    // Under the new score: the score with refusals counted, and for a pillar the tasks still scored.
    // Overall spans pillars, so a bare task count there would not say which pillar it counts.
    const coverage = key !== "overall" && info.coverage.length === 1 ? ` · ${info.coverage[0].scored}/${info.coverage[0].tasks}` : "";
    return { refusal: refusalLines(info, true),
      sub: <span className="score-sub">was {percent(base.tables[mode].summaries[agentKey(agent)].scores[key])}{coverage}</span> };
  };
  const agents = [...table.agents].sort((a, b) => {
    const x = value(a, sort.key), y = value(b, sort.key);
    return x === null ? y === null ? agentKey(a).localeCompare(agentKey(b)) : 1 : y === null ? -1 : (sort.ascending ? 1 : -1) * (x - y) || agentKey(a).localeCompare(agentKey(b));
  });
  const columns: [Sort, string][] = [["overall", "Overall"], ...pillars.map((pillar): [Sort, string] => [pillar, names[pillar]])];
  const columnPeers = Object.fromEntries(columns.map(([key]) => [key, peers(table.agents.map((agent) => value(agent, key)))]));
  const matrixAgents = [...matrixTable.agents].sort((a, b) =>
    (data.tables[evalsMode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(b)].scores.overall ?? -1) -
    (data.tables[evalsMode === "vanilla" ? "vanilla" : "skills"].summaries[agentKey(a)].scores.overall ?? -1));
  return <TooltipProvider delayDuration={200}><main id="main" className="page results-page">
    {data.demo && <aside className="banner"><strong>Demo data</strong> · Invented results for a board preview.</aside>}
    <header className="hero"><div className="hero-brand"><h1 id="hero-logo" aria-label="ETH Evals"><Logo id="hero-gradient" /></h1>
      <p className="hero-plate"><span><b>{data.counts.evals}</b> tasks</span><span><b>{data.counts.agents}</b> agents</span><span><b>{data.counts.runs.toLocaleString("en")}</b> trials</span></p></div>
      <p className="hero-tag">The Open Benchmark for AI on Ethereum</p>
      <p className="hero-desc">We evaluate agents used by developers, and the models behind them, on real Ethereum work. Every task, trial and trajectory is public, allowing anyone to run the same tasks.</p>
      <p className="hero-desc">We evaluate <Link href="/how-it-works/#hw-pillars">three pillars</Link>: <b>Concepts</b>, <b>Build</b>, and <b>Act</b>.</p>
    </header>
    <section id="leaderboard" className="results-section"><div className="section-head"><div><h2>Results</h2><p>The same work, with and without Ethereum skills.</p></div>
      <Link className="text-link" href={`/compare/?mode=${mode}${ignoring ? "&refusals=ignore" : ""}`}>Compare configurations →</Link></div>
      <div className="toolbar"><ModeToggle mode={mode} onChange={changeMode} /><p className="mode-note">{modeHints[mode]}</p>
        {(showRefusals || ignoring) && <RefusalSwitch ignoring={ignoring} />}</div>
      {ignoring && showRefusals && <RefusalStrip text={refusalStrip(ignored.tables[mode])} />}
      {agents.length ? <div className="table-shell"><div className="table-scroll" role="region" tabIndex={0} aria-label="Leaderboard. Scroll horizontally for all columns.">
        <table className="leaderboard"><caption className="sr-only">Configuration scores, sorted by {sort.key} {sort.ascending ? "ascending" : "descending"}</caption>
          <colgroup><col className="config-col" />{columns.map(([key]) => <col key={key} className="score-col" />)}</colgroup>
          <thead><tr><th scope="col" className="row-label">{mode === "vanilla" ? "Model" : "Configuration"}<small>model · agent</small></th>
            {columns.map(([key, name]) => <th key={key} scope="col" aria-sort={sort.key === key ? sort.ascending ? "ascending" : "descending" : "none"}>
              <button className="sort-button" onClick={() => setSort({ key, ascending: sort.key === key ? !sort.ascending : false })}>{name}{sort.key === key && (sort.ascending ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
            </th>)}</tr></thead><tbody>{agents.map((agent) => <tr key={agentKey(agent)}><th scope="row" className="row-label"><Configuration agent={agent} cost={table.summaries[agentKey(agent)].cost} tokens={table.summaries[agentKey(agent)].tokens} plan={table.summaries[agentKey(agent)].plan} /></th>
              {columns.map(([key]) => {
                const summary = key === "overall" ? table.summaries[agentKey(agent)] : table.pillars[key].cells[agentKey(agent)];
                return <td key={key}>
                  <Score score={value(agent, key)} lift={mode === "skills" ? data.lifts[agentKey(agent)]?.[key] : undefined}
                    peers={columnPeers[key]} best={key === "overall" ? "Best overall" : `Best in ${names[key]}`}
                    label={`${key === "overall" ? "Overall" : names[key]}, ${agentLabel(agent)}`}
                    empty={key !== "overall" && table.pillars[key].cells[agentKey(agent)].state === "empty" ? "No tasks yet" : summary.errors ? "No scored trials" : "No trials yet"}
                    missing={summary.missing}
                    onOpen={() => select({ agent, mode, pillar: key === "overall" ? undefined : key })} {...refusal(agent, key)} /></td>;
              })}
            </tr>)}</tbody></table></div>{mode === "skills" && <div className="table-note">+pp is the change over Internet.</div>}</div> :
        <div className="empty"><h3>{mode === "vanilla" ? "No model trials yet" : "No agent trials yet"}</h3><p>No published results match the current tasks. Browse the task catalog below.</p></div>}
      <div className="read-note" id="scoring"><b>How to read it:</b> Each row is an agent or a model, scored on three pillars: Concepts, Build, and Act. Overall averages the pillar scores, each counted by its number of tasks, up to {pillarTaskCap}. Click a pillar cell to see its tasks and every trial behind them. Tile color shows how close a score is to the best score in its column.</div>
    </section>
    <section id="evals" className="results-section"><div className="section-head"><div><h2>Results by task</h2><p>See each configuration’s task scores by pillar.</p></div>
      <ModeToggle mode={evalsMode} onChange={(value) => updateQuery({ evals: value })} label="Which task results" />
      <a className="button" href={`${repo}/blob/main/docs/add-a-task.md`} target="_blank" rel="noreferrer">How to add a task ↗</a></div>
      <div className="matrix-filters"><p className="eyebrow">{matrixRows.reduce((sum, { entries }) => sum + entries.length, 0)} tasks</p>
        <DomainFilter taskDomains={pillars.flatMap((pillar) => matrixTable.pillars[pillar].evals.map((entry) => data.evaluations[entry.id].domain))} domain={domain} />
      </div>
      <div className="table-shell"><div className="table-scroll matrix-scroll" role="region" tabIndex={0} aria-label="Task matrix. Scroll for more tasks and configurations.">
        <table className="matrix" role="table"><caption className="sr-only">Task scores by configuration</caption><thead role="rowgroup"><tr role="row"><th className="row-label" scope="col" role="columnheader">Task</th>
          {matrixAgents.map((agent) => <th key={agentKey(agent)} scope="col" role="columnheader"><Configuration agent={agent} cost={matrixTable.summaries[agentKey(agent)].cost} tokens={matrixTable.summaries[agentKey(agent)].tokens} plan={matrixTable.summaries[agentKey(agent)].plan} /></th>)}</tr></thead>
          <tbody role="rowgroup">{matrixRows.filter(({ entries }) => entries.length).map(({ pillar, entries }) => <Fragment key={pillar}><tr className="pillar-band" role="row"><th scope="colgroup" colSpan={matrixAgents.length + 1} role="columnheader"><span className="band-label">{names[pillar]}<small>{entries.length} tasks</small></span></th></tr>
            {entries.map((entry) => { const row = peers(matrixAgents.map((agent) => entry.cells[agentKey(agent)].score));
              return <tr role="row" key={entry.id} id={`eval-${entry.id.replaceAll("/", "-")}`}>
              <th scope="row" className="row-label" role="rowheader"><span className="eval-title">{data.evaluations[entry.id].title}</span><small>{entry.id}</small></th>
              {matrixAgents.map((agent) => { const cell = entry.cells[agentKey(agent)];
                return <td key={agentKey(agent)} role="cell"><span className="matrix-configuration" aria-hidden="true"><Configuration agent={agent} cost={cell.cost} tokens={cell.tokens} plan={matrixTable.summaries[agentKey(agent)].plan} /></span>
                  {(() => {
                    const refusal = refusedCount([cell]) > 0 ? taskRefusalLines(cell, ignoring) : undefined;
                    if (cell.state === "na" || (cell.score === null && !refusal)) return <span className="matrix-cell" data-empty title={[emptyTrialLabel(cell), ...cell.trials.map(trialHint)].join("\n")}>–</span>;
                    return <div className="score-wrap"><Hint text={taskHint(cell, row)}><button className="matrix-cell" {...tile(cell.score, row)}
                      aria-label={`${data.evaluations[entry.id].title}, ${agentLabel(agent)}. Task score ${percent(cell.score)}.${cell.missing ? ` ${unscored(cell.missing)}` : ""}${refusal ? ` ${sentences(refusal)}` : ""} Open details.`}
                      onClick={() => select({ evaluation: data.evaluations[entry.id], agent, mode: evalsMode })}>{percent(cell.score)}</button></Hint>
                      <CornerMarks missing={cell.score === null ? 0 : cell.missing} refusal={refusal} /></div>;
                  })()}</td>;
              })}
            </tr>; })}
          </Fragment>)}</tbody></table></div><div className="table-note">Task scores average trial scores. Tile color compares each score to the best on that task. Click a task score to see the instruction and trials.</div></div>
    </section>
    <noscript>Enable JavaScript to change modes and open trial details.</noscript>
  </main>
    <Sheet open={selection !== null} onOpenChange={(open) => { if (!open) close(); }}>
      {selection && <SheetContent>
        <SheetTitle className="sr-only">Task and trial details</SheetTitle><SheetDescription className="sr-only">Scores, instructions, checks, costs and trajectories.</SheetDescription>
        <Detail selection={selection} data={data} domain={domain} onSelect={select} /></SheetContent>}
    </Sheet>
  </TooltipProvider>;
}
