"use client";

import { useState } from "react";
import { updateQuery, useQuery } from "../../components/url-state";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../components/ui/tooltip";
import { domains, domainNames, taskDomain, type Domain } from "../../src/areas";
import { layers, pillars, type Eval } from "../../src/board";
import { layerNames, names, unwrapPrompt } from "../../src/labels";
import { repo } from "../../src/repo";

export function Tasks({ tasks }: { tasks: Eval[] }) {
  return <TaskList tasks={tasks} query={useQuery()} />;
}

function UpcomingDomain({ domain }: { domain: Domain }) {
  const [open, setOpen] = useState(false);
  return <Tooltip open={open} onOpenChange={setOpen} disableHoverableContent><TooltipTrigger asChild>
    <span className="inline-flex" tabIndex={0} onClick={(event) => { event.preventDefault(); setOpen(true); }}>
      <button type="button" className="badge border-dashed pointer-events-none" disabled>{domainNames[domain]}</button>
    </span></TooltipTrigger>
    <TooltipContent>{domainNames[domain]} tasks are coming soon.</TooltipContent>
  </Tooltip>;
}

export function TaskList({ tasks, query }: { tasks: Eval[]; query: URLSearchParams }) {
  const domain = domains.find((value) => value === query.get("domain"));
  const inDomain = tasks.filter((task) => !domain || taskDomain(task) === domain);
  const pillar = pillars.find((value) => value === query.get("pillar"));
  // Only Build tasks have a layer, so the layer filter needs Build selected.
  const layer = pillar === "build" ? layers.find((value) => value === query.get("layer")) : undefined;
  const areas = [...new Set(inDomain.flatMap((task) => task.area ? [task.area] : []))].sort((a, b) => a.localeCompare(b));
  const area = areas.find((value) => value === query.get("area"));
  const inArea = inDomain.filter((task) => !area || task.area === area);
  const inPillar = inDomain.filter((task) => (!pillar || task.pillar === pillar) && (!layer || task.layer === layer));
  const filtered = inPillar.filter((task) => !area || task.area === area);
  const ordered = pillars.flatMap((pillar) => filtered.filter((task) => task.pillar === pillar)
    .sort((a, b) => a.title.localeCompare(b.title)));
  return <TooltipProvider delayDuration={200}><main id="main" className="page tasks-page">
    <h1>Tasks</h1>
    <section aria-label="Task counts" className="task-counts">
      <div className="task-areas" role="group" aria-label="Filter by domain">
        {domains.map((value) => {
          const count = tasks.filter((task) => taskDomain(task) === value).length;
          return count === 0 ? <UpcomingDomain key={value} domain={value} /> :
            <button type="button" className="badge" key={value} aria-pressed={domain === value}
              onClick={() => updateQuery({ domain: domain === value ? null : value })}>{domainNames[value]} <span>{count}</span></button>;
        })}
      </div>
      <div className="task-totals" role="group" aria-label="Filter by pillar">
        <button type="button" aria-pressed={!pillar} onClick={() => updateQuery({ pillar: null, layer: null })}>
          <span className="eyebrow">Total tasks</span><span className="task-number">{inArea.length}</span>
        </button>
        {pillars.map((value) => <button type="button" key={value} className={`pillar-${value}`} aria-pressed={pillar === value}
          onClick={() => updateQuery({ pillar: pillar === value ? null : value, layer: null })}>
          <span className="eyebrow">{names[value]}</span>
          <span className="task-number">{inArea.filter((task) => task.pillar === value).length}</span>
        </button>)}
      </div>
      {pillar === "build" && <div className="task-areas pillar-build" role="group" aria-label="Filter Build tasks by layer">
        {layers.map((value) => {
          const count = inArea.filter((task) => task.pillar === "build" && task.layer === value).length;
          return <button type="button" className="badge" key={value} aria-pressed={layer === value} disabled={count === 0}
            onClick={() => updateQuery({ layer: layer === value ? null : value })}>{layerNames[value]} <span>{count}</span></button>;
        })}
      </div>}
      {areas.length > 0 && <div className="task-areas" role="group" aria-label="Filter by area">
        {areas.map((value) => {
          const count = inPillar.filter((task) => task.area === value).length;
          return <button type="button" className="badge" key={value} aria-pressed={area === value} disabled={count === 0}
            onClick={() => updateQuery({ area: area === value ? null : value })}>{value} <span>{count}</span></button>;
        })}
      </div>}
    </section>
    <div className="task-filter-status">
      <p role="status">{filtered.length} {filtered.length === 1 ? "task" : "tasks"}</p>
      {(domain || pillar || area) && <button type="button" className="button" onClick={() => updateQuery({ domain: null, pillar: null, area: null, layer: null })}>Clear filters</button>}
    </div>
    <section aria-label="All tasks" className="task-catalog">
      {ordered.map((task) => <details key={task.id} className="task-row">
        <summary><span className="task-title">{task.title}</span><span className="task-badges">
          <span className="badge">{domainNames[taskDomain(task)]}</span>
          <span className={`badge pillar-${task.pillar}`}>{names[task.pillar]}</span>
          {task.area && <span className="badge">{task.area}</span>}
        </span></summary>
        <div className="task-instruction"><p className="eyebrow">Instruction</p>
          <pre>{unwrapPrompt(task.instruction)}</pre>
          <a href={`${repo}/blob/main/tasks/${task.id}/README.md`} target="_blank" rel="noreferrer">README on GitHub ↗</a>
        </div>
      </details>)}
      {tasks.length === 0 && <p className="empty">No tasks yet.</p>}
      {tasks.length > 0 && filtered.length === 0 && <p className="empty">No tasks match these filters.</p>}
    </section>
  </main></TooltipProvider>;
}
