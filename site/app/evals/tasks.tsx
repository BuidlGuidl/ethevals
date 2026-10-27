import { pillars, type Eval } from "../../src/board";
import { names, unwrapPrompt } from "../../src/labels";
import { repo } from "../../src/repo";

export function Tasks({ tasks }: { tasks: Eval[] }) {
  const ordered = pillars.flatMap((pillar) => tasks.filter((task) => task.pillar === pillar)
    .sort((a, b) => a.title.localeCompare(b.title)));
  const areas = new Map<string, number>();
  for (const task of tasks) {
    if (task.area) areas.set(task.area, (areas.get(task.area) ?? 0) + 1);
  }
  return <main id="main" className="page tasks-page">
    <h1>Tasks</h1>
    <section aria-label="Task counts" className="task-counts">
      <dl className="task-totals">
        <div><dt className="eyebrow">Total tasks</dt><dd>{tasks.length}</dd></div>
        {pillars.map((pillar) => <div key={pillar}><dt className="eyebrow">{names[pillar]}</dt>
          <dd>{tasks.filter((task) => task.pillar === pillar).length}</dd></div>)}
      </dl>
      {areas.size > 0 && <dl className="hero-plate task-areas" aria-label="Tasks by area">
        {[...areas].sort(([a], [b]) => a.localeCompare(b)).map(([area, count]) =>
          <div key={area}><dt>{area}</dt><dd>{count}</dd></div>)}
      </dl>}
    </section>
    <section aria-label="All tasks" className="task-catalog">
      {ordered.map((task) => <details key={task.id} className="task-row">
        <summary><span className="task-title">{task.title}</span><span className="task-badges">
          <span className="badge">{names[task.pillar]}</span>
          {task.area && <span className="badge">{task.area}</span>}
        </span></summary>
        <div className="task-instruction"><p className="eyebrow">Instruction</p>
          <pre>{unwrapPrompt(task.instruction)}</pre>
          <a href={`${repo}/blob/main/tasks/${task.id}/README.md`} target="_blank" rel="noreferrer">README on GitHub ↗</a>
        </div>
      </details>)}
      {tasks.length === 0 && <p className="empty">No tasks yet.</p>}
    </section>
  </main>;
}
