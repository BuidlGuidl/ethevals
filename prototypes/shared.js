(function () {
  "use strict";
  const E = window.EVALS;
  const view = document.body.dataset.view;
  const root = document.getElementById("app");
  const expanded = new Set();
  const titles = { "1": "Mode tabs", "2": "Split columns", "3": "Grouped modes", "4": "Skills toggle" };
  const escape = value => String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  const percent = value => `${Math.round(value)}%`;
  const color = value => value < 25 ? "var(--red)" : value < 50 ? "var(--amber)" : "var(--green)";
  const modeName = mode => E.modes.find(item => item.id === mode).name;
  const pillarEvals = (pillar, vanillaOnly = false) => E.evals.filter(item => item.pillar === pillar && (!vanillaOnly || item.modes.includes("vanilla")));

  function evalStats(evaluation, agent, mode) {
    const result = evaluation.results[agent][mode];
    if (result === null) return { state: "na", score: null, count: 0, total: 0, runs: [] };
    if (!result.runs.length) return { state: "pending", score: null, count: 0, total: 1, runs: [] };
    return { state: "score", score: mean(result.runs.map(run => run.score)), count: 1, total: 1, runs: result.runs };
  }
  function pillarStats(pillar, agent, mode) {
    const applicable = pillarEvals(pillar).filter(item => item.modes.includes(mode));
    const stats = applicable.map(item => evalStats(item, agent, mode));
    const scores = stats.filter(item => item.state === "score");
    return {
      state: !applicable.length ? "na" : !scores.length ? "pending" : "score",
      score: mean(scores.map(item => item.score)), count: scores.length, total: applicable.length,
      runs: scores.flatMap(item => item.runs)
    };
  }
  function statsFor(kind, id, agent, mode) {
    return kind === "pillar" ? pillarStats(id, agent, mode) : evalStats(E.evals.find(item => item.id === id), agent, mode);
  }
  function passText(stats) {
    return `${stats.runs.filter(run => run.pass).length} of ${stats.runs.length} runs passed`;
  }
  function scoreCell(kind, id, agent, mode, compact = false) {
    const stats = statsFor(kind, id, agent.id, mode);
    const label = kind === "pillar" ? E.pillars.find(item => item.id === id).name : E.evals.find(item => item.id === id).title;
    const prefix = compact ? `<span class="mode-letter">${modeName(mode)[0]}</span>` : "";
    if (stats.state === "na") return `<span class="na" title="${escape(`${label} · ${modeName(mode)}: not applicable`)}">${prefix}<span aria-label="Not applicable">–</span></span>`;
    const content = stats.state === "pending" ? '<span class="pending">no run yet</span>' : `<span class="score">${percent(stats.score)}</span><span class="scorebar" aria-hidden="true"><i></i></span>`;
    const tooltip = stats.state === "pending" ? "Supported, no run yet" : `${passText(stats)} · ${stats.count} eval${stats.count === 1 ? "" : "s"}`;
    const coverage = kind === "pillar" ? `<span class="coverage">${compact ? `${stats.count}/${stats.total}` : `${stats.count} of ${stats.total} evals`}</span>` : "";
    return `<button class="cell" data-detail="${kind}" data-id="${id}" data-agent="${agent.id}" data-mode="${mode}" style="--score-color:${color(stats.score || 0)};--value:${stats.score || 0}%" title="${tooltip}" aria-label="${escape(`${label}, ${agent.name}, ${modeName(mode)}, ${stats.state === "score" ? percent(stats.score) : "no run yet"}. Open details`)}">${prefix}${content}${coverage}</button>`;
  }
  function liftMarkup(kind, id, agent) {
    const internet = statsFor(kind, id, agent, "internet");
    const skills = statsFor(kind, id, agent, "skills");
    if (internet.score === null || skills.score === null) return '<span class="lift muted" title="Both modes need runs">lift –</span>';
    // Compare the same evals when either mode has missing runs.
    const evaluations = kind === "pillar" ? pillarEvals(id) : [E.evals.find(item => item.id === id)];
    const pairs = evaluations.map(item => [evalStats(item, agent, "internet"), evalStats(item, agent, "skills")]).filter(pair => pair.every(item => item.state === "score"));
    const lift = Math.round(mean(pairs.map(pair => pair[1].score - pair[0].score)) || 0);
    return `<span class="lift ${lift < 0 ? "negative" : "positive"}" title="Skills minus Internet · ${pairs.length} matched evals">${lift >= 0 ? "+" : ""}${lift} pts${kind === "pillar" && (pairs.length !== internet.count || pairs.length !== skills.count) ? "*" : ""}</span>`;
  }
  function rowCells(kind, id, layout, mode) {
    return E.agents.map(agent => {
      const attr = `data-column="${agent.id}"`;
      if (layout === "split") return `<td ${attr}>${scoreCell(kind, id, agent, "internet")}</td><td ${attr} class="agent-end">${scoreCell(kind, id, agent, "skills")}${liftMarkup(kind, id, agent.id)}</td>`;
      if (layout === "grouped") return `<td ${attr} class="agent-end"><div class="mode-group">${E.modes.map(item => scoreCell(kind, id, agent, item.id, true)).join("")}</div></td>`;
      return `<td ${attr}>${scoreCell(kind, id, agent, mode)}</td>`;
    }).join("");
  }
  function table(layout, mode, boardId, vanillaOnly = false) {
    const head = E.agents.map(agent => `<th scope="col${layout === "split" ? "group" : ""}" data-column="${agent.id}" ${layout === "split" ? 'colspan="2"' : ""}><span class="agent-name">${agent.name}</span><span class="subline">${agent.harness} · ${agent.effort}</span></th>`).join("");
    const subhead = layout === "split" ? `<tr class="subhead">${E.agents.map(agent => `<th scope="col" data-column="${agent.id}">no skills</th><th scope="col" class="agent-end" data-column="${agent.id}">skills</th>`).join("")}</tr>` : "";
    const body = E.pillars.map(pillar => {
      const evaluations = pillarEvals(pillar.id, vanillaOnly);
      const key = `${boardId}-${pillar.id}`;
      const open = expanded.has(key);
      const heading = `<tr class="pillar-row"><th class="row-label" scope="row"><button class="pillar-toggle" data-expand="${key}" aria-expanded="${open}" aria-controls="${key}"><span class="chevron" aria-hidden="true">›</span>${pillar.name}<span class="subline">${evaluations.length} evals</span></button></th>${rowCells("pillar", pillar.id, layout, mode)}</tr>`;
      const rows = evaluations.map(item => `<tr class="eval-row"><th scope="row" class="row-label"><span class="eval-title">${escape(item.title)}</span><span class="eval-id">${item.id}</span><span class="chips"><span class="chip">${item.type}</span><span class="chip">${item.grader}</span></span></th>${rowCells("eval", item.id, layout, mode)}</tr>`).join("");
      const empty = `<tr><td colspan="${1 + E.agents.length * (layout === "split" ? 2 : 1)}" class="muted">No Vanilla-capable evals in this pillar.</td></tr>`;
      return `<tbody>${heading}</tbody><tbody id="${key}" ${open ? "" : "hidden"}>${rows || empty}</tbody>`;
    }).join("");
    return `<div class="table-shell"><div class="table-scroll" tabindex="0" role="region" aria-label="${layout === "grouped" ? "All modes" : layout === "split" ? "Internet and Skills" : modeName(mode)} scores. Scroll horizontally for all agents."><table class="board ${layout}"><caption hidden>${titles[view]} · agents by pillar and eval</caption><thead><tr><th scope="col" class="row-label" ${layout === "split" ? 'rowspan="2"' : ""}>Pillar / eval<span class="subline">Click a pillar to unfold</span></th>${head}</tr>${subhead}</thead>${body}</table></div><div class="table-note"><span>Click a score for runs · – not applicable · <em>no run yet</em> supported, unrun</span><span>${layout === "split" ? "Lift uses matched evals · * coverage differs" : "Pillar score = mean of completed eval scores"}</span></div></div>`;
  }
  function nav() {
    const base = view === "index" ? "" : "../";
    return `<nav class="topnav" aria-label="Prototype views"><a class="brand" href="${base}index.html">ETH Evals <span class="muted">/ prototypes</span></a><a href="${base}index.html" ${view === "index" ? 'aria-current="page"' : ""}>Index</a>${Object.entries(titles).map(([id, title]) => `<a href="${base}${id}/index.html" ${view === id ? 'aria-current="page"' : ""}>${id} <span>${title}</span></a>`).join("")}${view === "2" ? '<a class="jump" href="#vanilla">Pre-training ↓</a>' : ""}</nav>`;
  }
  function strip() {
    return `<section class="pillar-strip" aria-label="Pillars">${E.pillars.map(pillar => `<div class="pillar-intro"><h2>${pillar.name}<span class="subline">${pillarEvals(pillar.id).length} evals</span></h2><p>${pillar.description}</p></div>`).join("")}</section>`;
  }
  function segmented(items, selected, action, label, className = "segmented") {
    return `<div class="${className}" role="group" aria-label="${label}">${items.map(([id, title]) => `<button data-${action}="${id}" aria-pressed="${id === selected}">${title}</button>`).join("")}</div>`;
  }
  function readState() {
    const params = new URLSearchParams(location.hash.slice(1));
    return {
      mode: E.modes.some(mode => mode.id === params.get("mode")) ? params.get("mode") : "skills",
      tab: params.get("tab") === "vanilla" ? "vanilla" : "main",
      skills: params.get("skills") !== "off"
    };
  }
  let state = readState();
  function updateHash() {
    const hash = view === "1" ? `mode=${state.mode}` : `tab=${state.tab}&skills=${state.skills ? "on" : "off"}`;
    if (location.hash !== `#${hash}`) location.hash = hash;
    else renderBoard();
  }
  function renderBoard() {
    const content = document.getElementById("boards");
    const active = document.activeElement;
    const focusKey = active && (active.dataset.modeSelect ? `[data-mode-select="${active.dataset.modeSelect}"]` : active.dataset.tab ? `[data-tab="${active.dataset.tab}"]` : active.dataset.skills ? `[data-skills="${active.dataset.skills}"]` : null);
    if (view === "1") {
      content.innerHTML = `<section class="board-section"><div class="toolbar">${segmented(E.modes.map(mode => [mode.id, mode.name]), state.mode, "mode-select", "Mode")}<span class="muted">${E.modes.find(mode => mode.id === state.mode).description}</span></div>${table("single", state.mode, "main")}</section>`;
    } else if (view === "2") {
      content.innerHTML = `<section class="board-section"><div class="toolbar"><h2>Internet + Skills</h2><span class="muted">Paired scores · lift in percentage points</span></div>${table("split", "internet", "main")}</section><section id="vanilla" class="board-section"><h2>Pre-training (Vanilla)</h2><p class="muted">What the agent knows without internet. Only Vanilla-capable evals.</p>${table("single", "vanilla", "vanilla", true)}</section>`;
    } else if (view === "3") {
      content.innerHTML = `<section class="board-section"><div class="legend"><span><b>V</b> Vanilla · no internet</span><span><b>I</b> Internet · no skills</span><span><b>S</b> Skills · internet + ethskills</span><span>Coverage below scores: completed / supported evals</span></div>${table("grouped", "skills", "main")}</section>`;
    } else {
      const vanilla = state.tab === "vanilla";
      content.innerHTML = `<section class="board-section">${segmented([["main", "Main board"], ["vanilla", "Pre-training (Vanilla)"]], state.tab, "tab", "Board", "page-tabs")}<div class="toolbar">${vanilla ? '<p class="muted">What the agent knows without internet. Only Vanilla-capable evals.</p>' : segmented([["on", "With skills"], ["off", "Without skills"]], state.skills ? "on" : "off", "skills", "Skills")}<span class="muted">${vanilla ? "No internet" : "Internet enabled"}</span></div>${table("single", vanilla ? "vanilla" : state.skills ? "skills" : "internet", "main", vanilla)}</section>`;
    }
    if (focusKey) content.querySelector(focusKey)?.focus();
  }
  function indexPage() {
    const descriptions = {
      "1": ["One mode at a time. Seven agent columns stay in place.", "Switch modes to compare scores and coverage."],
      "2": ["Internet and Skills sit side by side, with the lift below.", "Vanilla has a separate table beneath the main board."],
      "3": ["Every cell holds V / I / S. All modes share one table.", "Read across agents or compare modes within a cell."],
      "4": ["Toggle skills on the main board. One score per cell.", "Open the pre-training tab to see Vanilla alone."]
    };
    return `<div class="view-list">${Object.entries(titles).map(([id, title]) => `<a class="view-link" href="${id}/index.html"><span class="view-number">0${id}</span><strong>${title}</strong><p>${descriptions[id][0]}<br>${descriptions[id][1]}</p><span class="arrow" aria-hidden="true">↗</span></a>`).join("")}</div>`;
  }
  root.innerHTML = `${nav()}<main><header class="page-heading"><div><p class="eyebrow">Throwaway prototype · fake results</p><h1>${view === "index" ? "Same results, four views" : `${view} / ${titles[view]}`}</h1></div><span class="muted mono">${E.evals.length} evals · ${E.agents.length} agents · 3 modes</span></header>${strip()}${view === "index" ? indexPage() : '<div id="boards" class="board-section"></div>'}<p class="footer-note">Synthetic data. Scores average runs, then evals. Missing runs never count as zero. Prototype pass cutoff: ${E.passThreshold}%.</p></main><dialog id="detail" aria-labelledby="detail-title"><div id="detail-content"></div></dialog>`;
  if (view !== "index") renderBoard();
  const dialog = document.getElementById("detail");
  const detailContent = document.getElementById("detail-content");
  let detail = null;
  let opener = null;
  function openDetail(kind, id, agent, mode) {
    if (!dialog.open) opener = document.activeElement;
    detail = { kind, id, agent, mode, run: 0 };
    renderDetail();
    if (!dialog.open) dialog.showModal();
    document.getElementById("close-detail").focus();
  }
  function renderDetail() {
    const agent = E.agents.find(item => item.id === detail.agent);
    const evaluation = E.evals.find(item => item.id === detail.id);
    const pillar = E.pillars.find(item => item.id === (detail.kind === "pillar" ? detail.id : evaluation.pillar));
    const stats = statsFor(detail.kind, detail.id, agent.id, detail.mode);
    const title = detail.kind === "pillar" ? pillar.name : evaluation.title;
    const summary = stats.state === "score" ? `${passText(stats)} · ${percent(stats.score)}` : stats.state === "na" ? "Not applicable" : "No run yet";
    let body;
    if (detail.kind === "pillar") {
      body = `<p class="muted">${stats.count} of ${stats.total} supported evals ran. Each completed eval has equal weight.</p><div class="eval-list">${pillarEvals(pillar.id).map(item => {
        const score = evalStats(item, agent.id, detail.mode);
        return `<button data-detail="eval" data-id="${item.id}" data-agent="${agent.id}" data-mode="${detail.mode}"><span>${escape(item.title)}<span class="eval-id">${item.id} · ${item.type} · ${item.grader}</span></span><span class="list-value" style="color:${score.score === null ? "var(--muted)" : color(score.score)}">${score.state === "na" ? "–" : score.state === "pending" ? "no run yet" : percent(score.score)} ›</span></button>`;
      }).join("")}</div>`;
    } else {
      const back = `<button class="back-button" data-detail="pillar" data-id="${pillar.id}" data-agent="${agent.id}" data-mode="${detail.mode}">← ${pillar.name} evals</button>`;
      if (stats.state !== "score") {
        body = `${back}<p>${stats.state === "na" ? "This eval does not support this mode." : "This mode is supported. No runs have been recorded."}</p><h3>Prompt</h3><pre>${escape(evaluation.prompt)}</pre>`;
      } else {
        body = `${back}<div class="table-scroll"><table class="run-table"><thead><tr><th>Run</th><th>Score</th><th>Result</th><th>Time</th><th>Tokens in / out</th><th>Cost</th></tr></thead><tbody>${stats.runs.map((run, index) => `<tr class="${index === detail.run ? "selected" : ""}"><td><button data-run="${index}" aria-expanded="${index === detail.run}" aria-controls="selected-run">Run ${index + 1}</button></td><td>${percent(run.score)}</td><td class="${run.pass ? "positive" : "negative"}">${run.pass ? "Pass" : "Fail"}</td><td>${run.durationSec}s</td><td>${run.tokens.input.toLocaleString("en-US")} / ${run.tokens.output.toLocaleString("en-US")}</td><td>$${run.cost.toFixed(4)}</td></tr>`).join("")}</tbody></table></div><div id="selected-run" class="run-detail">${runDetail(stats.runs[detail.run], evaluation)}</div>`;
      }
    }
    detailContent.innerHTML = `<header class="drawer-header"><div class="drawer-heading"><div class="drawer-caption">${pillar.name} · ${modeName(detail.mode)} · ${agent.name}<br>${agent.harness} · ${agent.effort}</div><h2 id="detail-title">${escape(title)}</h2><div class="drawer-summary"><span class="mono">${summary}</span><span class="subline">Fake run data · pass ≥ ${E.passThreshold}%</span></div></div><button id="close-detail" class="close-button" aria-label="Close details">Close ×</button></header><div class="drawer-content">${body}</div>`;
  }
  function runDetail(run, evaluation) {
    const grader = run.grader.kind === "judge" ? `${run.grader.rubric.map(item => `<div class="rubric-line"><span>${item.name}</span><span class="mono">${percent(item.score)}</span></div>`).join("")}<p class="muted">${escape(run.grader.note)}</p>` : `<div class="grader-checks">${run.grader.checks.map(check => `<span><span class="${check.pass ? "positive" : "negative"}">${check.pass ? "✓" : "✗"}</span> ${escape(check.name)}</span>`).join("")}</div>`;
    const diff = run.diff.split("\n").map(line => `<span class="${line.startsWith("+") ? "positive" : line.startsWith("-") ? "negative" : ""}">${escape(line)}</span>`).join("\n");
    return `<h3>Run ${detail.run + 1}</h3><section><h3>Prompt</h3><pre>${escape(evaluation.prompt)}</pre></section><section><h3>Transcript excerpt</h3><pre>${escape(run.transcript.join("\n"))}</pre><span class="disabled-link" role="link" aria-disabled="true" title="Prototype only">Open full transcript</span></section><section><h3>Files / diff</h3><div class="file-list">${run.files.map(escape).join("<br>")}</div><pre>${diff}</pre></section><section><h3>Grader · ${evaluation.grader}</h3>${grader}</section>`;
  }
  document.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.id === "close-detail") dialog.close();
    else if (button.dataset.detail) openDetail(button.dataset.detail, button.dataset.id, button.dataset.agent, button.dataset.mode);
    else if (button.dataset.run !== undefined) {
      detail.run = Number(button.dataset.run);
      renderDetail();
      detailContent.querySelector(`[data-run="${detail.run}"]`).focus();
    } else if (button.dataset.expand) {
      const key = button.dataset.expand;
      const open = !expanded.has(key);
      if (open) expanded.add(key); else expanded.delete(key);
      button.setAttribute("aria-expanded", String(open));
      document.getElementById(key).hidden = !open;
    } else if (button.dataset.modeSelect) {
      state.mode = button.dataset.modeSelect;
      updateHash();
    } else if (button.dataset.tab) {
      state.tab = button.dataset.tab;
      updateHash();
    } else if (button.dataset.skills) {
      state.skills = button.dataset.skills === "on";
      updateHash();
    }
  });
  dialog.addEventListener("click", event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
  dialog.addEventListener("close", () => opener?.focus());
  window.addEventListener("hashchange", () => {
    if (view !== "1" && view !== "4") return;
    state = readState();
    renderBoard();
  });
  function highlightColumn(event) {
    const cell = event.target.closest("[data-column]");
    const tableElement = event.target.closest(".board");
    if (!tableElement) return;
    const column = event.type === "pointerout" ? event.relatedTarget?.closest?.("[data-column]")?.dataset.column : cell?.dataset.column;
    tableElement.querySelectorAll("[data-column]").forEach(item => item.classList.toggle("column-hover", item.dataset.column === column));
  }
  document.addEventListener("pointerover", highlightColumn);
  document.addEventListener("pointerout", highlightColumn);
})();
