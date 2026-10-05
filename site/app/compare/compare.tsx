"use client";

import Link from "next/link";
import { agentKey, pillars, type BoardData, type Mode, type Agent } from "../../src/board";
import { Configuration } from "../../components/configuration";
import { modelOnlyNote, names } from "../../src/labels";
import { ModeToggle } from "../../components/mode-toggle";
import { Hint, formulas, percent, money, pp } from "../../components/scores";
import { TooltipProvider } from "../../components/ui/tooltip";
import { ToggleGroup, ToggleGroupItem } from "../../components/ui/toggle-group";
import { updateQuery, useQuery } from "../../components/url-state";

export default function Compare({ data }: { data: BoardData }) {
  const query = useQuery();
  const mode: Mode = query.get("mode") === "skills" ? "skills" : query.get("mode") === "vanilla" ? "vanilla" : "internet";
  const table = data.tables[mode];
  const keys = table.agents.map(agentKey);
  const defaults = [...table.agents].sort((a, b) => (table.summaries[agentKey(b)].scores.overall ?? -1) - (table.summaries[agentKey(a)].scores.overall ?? -1)).slice(0, 3).map(agentKey);
  const chosen = query.has("pick") ? parseSelection(query.get("pick"), keys) : defaults;
  const selected = chosen.map((key) => table.agents.find((agent) => agentKey(agent) === key)!);
  const metrics: { label: string; formula: string; value: (agent: Agent) => number | null; format: (value: number | null) => string; lower?: boolean }[] = [
    { label: "Overall", formula: formulas.overall, value: (agent) => table.summaries[agentKey(agent)].scores.overall, format: percent },
    ...pillars.map((pillar) => ({ label: names[pillar], formula: formulas.pillar, value: (agent: Agent) => table.summaries[agentKey(agent)].scores[pillar], format: percent })),
    ...(mode === "skills" ? [{ label: "Lift from skills", formula: formulas.lift, value: (agent: Agent) => data.lifts[agentKey(agent)]?.overall ?? null, format: pp }] : []),
    { label: "$ / pass ↓", formula: formulas.cost, value: (agent) => table.summaries[agentKey(agent)].costPerPass, format: money, lower: true },
    { label: "Tokens per run ↓", formula: formulas.tokens, value: (agent) => table.summaries[agentKey(agent)].medianTokens, format: (value) => value === null ? "–" : value.toLocaleString("en"), lower: true },
  ];
  return <TooltipProvider delayDuration={200}><main id="main" className="page compare-page">
    {data.demo && <aside className="banner"><strong>Demo data</strong> · Invented results for a board preview.</aside>}
    <p className="eyebrow"><Link href={`/?mode=${mode}`}>Results</Link> / Compare</p>
    <div className="section-head"><h1>Compare configurations</h1><Link className="button" href={`/?mode=${mode}`}>← Back to results</Link></div>
    <div className="pick-row"><p className="muted">Select up to 5:</p><ToggleGroup type="multiple" className="configuration-picks" value={chosen}
      onValueChange={(values) => { if (values.length <= 5) updateQuery({ pick: JSON.stringify(values) }); }} aria-label="Configurations to compare">
      {table.agents.map((agent) => <ToggleGroupItem key={agentKey(agent)} value={agentKey(agent)} disabled={!chosen.includes(agentKey(agent)) && chosen.length >= 5}>
        <Configuration agent={agent} /></ToggleGroupItem>)}
    </ToggleGroup></div>
    <ModeToggle mode={mode} onChange={(value) => updateQuery({ mode: value, pick: JSON.stringify(chosen) })} />
    {mode === "vanilla" && <p className="mode-note">{modelOnlyNote}</p>}
    {selected.length ? <div className="table-shell"><div className="table-scroll" role="region" tabIndex={0} aria-label="Configuration comparison">
      <table className="comparison"><caption className="sr-only">Compare scores and costs for selected configurations</caption><thead><tr><th scope="col">Metric</th>
        {selected.map((agent, index) => <th scope="col" key={agentKey(agent)}><span className={`compare-swatch tone-${index}`} /><Configuration agent={agent} /></th>)}</tr></thead>
        <tbody>{metrics.map((metric) => {
          const values = selected.map(metric.value), scored = values.filter((value): value is number => value !== null);
          const best = metric.lower ? Math.min(...scored) : Math.max(...scored);
          return <tr key={metric.label}><th scope="row">{metric.label}</th>{values.map((value, index) => <td key={agentKey(selected[index])} className={value !== null && value === best ? "best" : ""}>
            <Hint text={metric.formula}><span tabIndex={0}>{metric.format(value)}</span></Hint></td>)}</tr>;
        })}</tbody></table></div><div className="table-note">Best value in each row is highlighted · ↓ lower is better</div></div> :
      <div className="empty"><h3>{table.agents.length ? "Select configurations to compare" : "No configurations yet"}</h3><p>Published results supply the scores and costs.</p></div>}
  </main></TooltipProvider>;
}

// Ignore malformed or stale configuration links without hiding the page.
function parseSelection(value: string | null, keys: string[]): string[] {
  try { const parsed: unknown = JSON.parse(value ?? "[]");
    return Array.isArray(parsed) ? [...new Set(parsed.filter((key): key is string => typeof key === "string" && keys.includes(key)))].slice(0, 5) : [];
  } catch { return []; }
}
