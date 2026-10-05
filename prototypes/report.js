/* View 5 · Report. Builds on view 4, with Vanilla kept apart where it is not comparable:
   - Ranking, Lift, Matrix and Pareto compare agents: Without skills vs With skills (same evals).
   - Vanilla (pre-training, pi with tools off) has its own page and hero card; it is compared with
     the agent modes (V → I → S) only on the evals all three share. It also shows on each eval page
     and as a separate block in Compare. */
(function () {
  "use strict";
  const E = window.EVALS, S = E.suite;
  const root = document.getElementById("app");
  const esc = v => String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = x => isNaN(x) ? "–" : Math.round(x * 100) + "%";
  const pm = s => isNaN(s.p) ? "" : "±" + Math.round((s.hi - s.lo) * 50);
  const pp = x => (x >= 0 ? "+" : "−") + Math.abs(Math.round(x * 100)) + "pp";
  const usd = x => isNaN(x) ? "–" : x < .01 ? "$" + x.toFixed(4) : "$" + x.toFixed(3);
  const tok = x => isNaN(x) ? "–" : x >= 1000 ? Math.round(x / 1000) + "k" : Math.round(x) + "";
  const color = p => isNaN(p) ? "var(--muted)" : p >= .8 ? "var(--green)" : p >= .5 ? "var(--amber)" : "var(--red)";
  const modeName = id => ({ vanilla: "Pre-training (Vanilla)", internet: "Without skills", skills: "With skills" })[id];
  const agentById = id => E.agents.find(a => a.id === id);
  const evalById = id => E.evals.find(e => e.id === id);
  const harnessFor = (a, mode) => mode === "vanilla" ? "pi · tools off" : `${a.harness} ${a.version} · ${a.effort}`;

  // ---------- stats ----------
  function wilson(k, n, z = 1.96) {
    if (!n) return { p: NaN, lo: NaN, hi: NaN, k, n };
    const p = k / n, d = 1 + z * z / n, c = p + z * z / (2 * n), m = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n));
    return { p, lo: (c - m) / d, hi: (c + m) / d, k, n };
  }
  const runsOf = (ev, agent, mode) => { const r = ev.results[agent][mode]; return r ? r.runs : []; };
  function stats(agent, mode, evFilter) {
    const evs = E.evals.filter(ev => ev.modes.includes(mode) && (!evFilter || evFilter(ev)));
    const all = evs.flatMap(ev => runsOf(ev, agent, mode));
    const rs = all.filter(r => !r.invalid);
    const k = rs.filter(r => r.pass).length;
    const cost = rs.reduce((s, r) => s + r.cost, 0);
    const toks = rs.map(r => r.tokens.input + r.tokens.output).sort((a, b) => a - b);
    return { ...wilson(k, rs.length), evals: evs.length, ran: evs.filter(ev => runsOf(ev, agent, mode).length).length,
      costPerPass: k ? cost / k : NaN, tokMed: toks.length ? toks[Math.floor(toks.length / 2)] : NaN,
      read: mode === "skills" && rs.length ? rs.filter(r => r.skillRead).length / rs.length : NaN,
      invalid: all.length - rs.length };
  }
  const common = ev => ev.modes.length === 3;
  const nCommon = pillar => E.evals.filter(ev => common(ev) && (!pillar || ev.pillar === pillar)).length;

  function segmented(items, selected, key) {
    return `<div class="segmented" role="group">${items.map(([id, t]) => `<button data-${key}="${id}" aria-pressed="${id === selected}">${t}</button>`).join("")}</div>`;
  }
  function runDot(r) {
    const c = r.invalid ? "x" : r.end === "time limit" ? "t" : r.pass ? "p" : "f";
    const l = r.invalid ? "invalid: fetched our repo" : r.end === "time limit" ? "time limit" : r.pass ? "pass" : "fail";
    return `<a class="dot ${c}" href="#/run/${encodeURIComponent(r.id)}" title="Run ${r.k}: ${l}" aria-label="Run ${r.k}: ${l}"></a>`;
  }

  // ---------- provider colours ----------
  const orgOf = { opus: "Anthropic", fable: "Anthropic", sonnet: "Anthropic", astra: "OpenAI", glm: "Z.ai", kimi: "Moonshot", deepseek: "DeepSeek" };
  const orgColor = { Anthropic: "#d97757", OpenAI: "#d4d4d4", "Z.ai": "#5b8cff", Moonshot: "#a78bfa", DeepSeek: "#38bdf8" };

  // ---------- view state ----------
  const st = { view: "ranking", mode: "skills", pillar: "all", cell: "", cmp: [], cmpMode: "skills", base: "all", pset: "both", px: "cost" };
  const VIEWS = [["ranking", "Ranking"], ["lift", "Lift from skills"], ["matrix", "Matrix"], ["pareto", "Pareto"]];
  function readHash() {
    const h = location.hash.slice(1);
    if (h.startsWith("/")) return { route: h.slice(1).split("/") };
    const q = new URLSearchParams(h);
    if (VIEWS.some(v => v[0] === q.get("view"))) st.view = q.get("view");
    if (["internet", "skills"].includes(q.get("mode"))) st.mode = q.get("mode");
    if (q.get("mode") === "gap") { st.mode = "skills"; st.view = "lift"; st.base = "shared"; }
    if (["all", "shared"].includes(q.get("base"))) st.base = q.get("base");
    if (["all", ...E.pillars.map(p => p.id)].includes(q.get("pillar"))) st.pillar = q.get("pillar");
    st.cell = q.get("cell") || "";
    return { route: [] };
  }
  const boardHash = () => `#view=${st.view}&mode=${st.mode}&pillar=${st.pillar}${st.view === "lift" && st.base === "shared" ? "&base=shared" : ""}${st.cell ? "&cell=" + st.cell : ""}`;
  const inPillar = ev => st.pillar === "all" || ev.pillar === st.pillar;
  const pillarName = () => st.pillar === "all" ? "All pillars" : E.pillars.find(p => p.id === st.pillar).name;
  const heat = p => isNaN(p) || p < .5 ? "transparent" : `color-mix(in srgb, var(--green) ${Math.round(Math.min(1, (p - .4) / .5) * 38)}%, transparent)`;

  // ---------- cells ----------
  function cellPR(s, attrs) {
    if (!s.n) return `<span class="na" title="No runs in this mode">–</span>`;
    return `<button class="pr" ${attrs} style="--score-color:${color(s.p)};background:${heat(s.p)}" title="${s.k} of ${s.n} runs passed${s.ran < s.evals ? ` · ${s.ran} of ${s.evals} evals ran` : ""}${s.invalid ? ` · ${s.invalid} invalid run excluded` : ""}"><span class="v">${pct(s.p)}<small>${pm(s)}</small></span><span class="wbar"><i style="width:${s.p * 100}%"></i><u style="left:${s.lo * 100}%;width:${(s.hi - s.lo) * 100}%"></u></span><span class="n">${s.k}/${s.n} runs${s.invalid ? ` · <span class="neg">${s.invalid} invalid</span>` : ""}</span>${s.ran < s.evals ? `<span class="n" style="color:var(--amber)" title="Supported evals without runs are left out, not counted as zero">${s.ran} of ${s.evals} evals ran</span>` : ""}</button>`;
  }
  // V → I → S track: three dots on a 0–100% scale, joined in order, so a drop reads as a drop.
  function track(points) {
    const segs = [];
    for (let k = 1; k < points.length; k++) {
      const a = points[k - 1], b = points[k], lo = Math.min(a.p, b.p), hi = Math.max(a.p, b.p);
      segs.push(`<span class="dseg ${b.p < a.p ? "down" : ""}" style="left:${lo * 100}%;width:${(hi - lo) * 100}%;--c:${b.c}"></span>`);
    }
    return `<span class="dtrack"><span class="dticks"><i></i><i></i><i></i></span>${segs.join("")}${points.map(pt => `<span class="dpt" style="left:${pt.p * 100}%;background:${pt.c}" title="${pt.l} ${pct(pt.p)}"></span>`).join("")}</span>`;
  }
  function cellGap(agent, filter, attrs) {
    const f = ev => common(ev) && filter(ev);
    const v = stats(agent, "vanilla", f), i = stats(agent, "internet", f), s = stats(agent, "skills", f);
    const n = E.evals.filter(f).length;
    if (!v.n) {
      const i2 = stats(agent, "internet", filter), s2 = stats(agent, "skills", filter);
      if (!i2.n) return `<span class="na">–</span>`;
      return `<button class="gap2" ${attrs} title="No Vanilla evals here: Internet → Skills only"><span class="t"><span><em class="lv">I</em> ${Math.round(i2.p * 100)} <em class="ls">S</em> ${Math.round(s2.p * 100)}</span><b class="${s2.p >= i2.p ? "pos" : "neg"}">S−I ${pp(s2.p - i2.p)}</b></span>${track([{ p: i2.p, c: "var(--i)", l: "Internet" }, { p: s2.p, c: "var(--s)", l: "Skills" }])}<span class="n">no Vanilla evals · Internet vs Skills</span></button>`;
    }
    const low = n < 5;
    return `<button class="gap2" ${attrs}><span class="t"><span><em class="lvv">V</em> ${Math.round(v.p * 100)} <em class="lv">I</em> ${Math.round(i.p * 100)} <em class="ls">S</em> ${Math.round(s.p * 100)}</span><b class="${s.p >= v.p ? "pos" : "neg"}">S−V ${pp(s.p - v.p)}</b></span>${track([{ p: v.p, c: "var(--v)", l: "Vanilla" }, { p: i.p, c: "var(--i)", l: "Internet" }, { p: s.p, c: "var(--s)", l: "Skills" }])}<span class="n" ${low ? 'style="color:var(--amber)"' : ""}>${n} shared eval${n === 1 ? "" : "s"} · ${v.n + i.n + s.n} runs${low ? " · few evals, read with care" : ""}</span></button>`;
  }


  // ---------- KPIs ----------
  function kpis() {
    const pool = (mode, f) => E.evals.filter(ev => ev.modes.includes(mode) && f(ev)).flatMap(ev => E.agents.flatMap(a => runsOf(ev, a.id, mode))).filter(r => !r.invalid);
    const tot = (mode, f = inPillar) => { const rs = pool(mode, f); const k = rs.filter(r => r.pass).length; const cost = rs.reduce((s, r) => s + r.cost, 0); return { ...wilson(k, rs.length), cpp: cost / k, read: rs.filter(r => r.skillRead).length / rs.length }; };
    const i = tot("internet"), s = tot("skills"), v = tot("vanilla");
    const nIS = E.evals.filter(ev => ev.modes.includes("internet") && inPillar(ev)).length, nV = E.evals.filter(ev => ev.modes.includes("vanilla") && inPillar(ev)).length;
    const sv = tot("skills", ev => common(ev) && inPillar(ev));
    const card = (cls, dot, name, st8, lines, href) => `<${href ? `a href="${href}"` : "div"} class="kcard ${cls}"><span class="lbl"><i style="background:${dot}"></i>${name}</span><span class="big">${st8.n ? pct(st8.p) : "–"}<small>${st8.n ? pm(st8) : ""}</small></span>${lines.map(l => `<span class="kline">${l}</span>`).join("")}</${href ? "a" : "div"}>`;
    return `<div class="kcap">${pillarName()}</div><div class="kcards k7">
      ${card("", "var(--i)", "Without skills", i, [`${i.k}/${i.n} runs · ${nIS} evals`, `${usd(i.cpp)}/pass`])}
      ${card("", "var(--s)", "With skills", s, [`${s.k}/${s.n} runs · ${nIS} evals`, `<span class="${s.p >= i.p ? "pos" : "neg"}">${pp(s.p - i.p)}</span> vs without · same evals`, `skill read ${pct(s.read)}`])}
      ${card("pre", "var(--v)", "Pre-training knowledge", v, [...(nV ? [`${v.k}/${v.n} runs · ${nV} evals`, `model only · pi, no tools`] : ["no knowledge evals in this pillar", "every eval here needs tools"]), `<span class="kgo">See pre-training results →</span>`], `#/pretraining/${st.pillar}`)}
    </div>`;
  }


  // ---------- Ranking view ----------
  function columnsForPillar() {
    if (st.pillar === "all") return [{ key: "all", name: "Overall", f: () => true, overall: true }, ...E.pillars.map(p => ({ key: p.id, name: p.name, f: ev => ev.pillar === p.id, color: `var(--p-${p.id})` }))];
    const p = E.pillars.find(x => x.id === st.pillar);
    const types = ["Quiz", "Scenario", "Build", "Act"].filter(t => E.evals.some(ev => ev.pillar === p.id && ev.type === t));
    return [{ key: p.id, name: p.name, f: ev => ev.pillar === p.id, overall: true, color: `var(--p-${p.id})` }, ...types.map(t => ({ key: p.id + "-" + t, name: t, f: ev => ev.pillar === p.id && ev.type === t }))];
  }
  function viewRanking() {
    const gap = st.mode === "gap", mode = gap ? "skills" : st.mode;
    const evSet = f => E.evals.filter(ev => f(ev) && (gap ? common(ev) : ev.modes.includes(mode))).map(ev => ev.id).join(",");
    const allCols = columnsForPillar();
    const cols = allCols.filter((c, i) => i === 0 || !evSet(c.f) || evSet(c.f) !== evSet(allCols[0].f) || false).filter((c, i) => i === 0 || evSet(c.f) !== evSet(allCols[0].f));
    const rows = E.agents.map(a => ({ a, s: gap ? stats(a.id, "skills", ev => common(ev) && inPillar(ev)) : stats(a.id, mode, inPillar) })).sort((x, y) => (y.s.p || 0) - (x.s.p || 0));
    // True when o beats r significantly (two-proportion test, 95%).
    const beats = (o, r) => { if (!o.s.n || !r.s.n) return false; const se = Math.sqrt(o.s.p * (1 - o.s.p) / o.s.n + r.s.p * (1 - r.s.p) / r.s.n); return se > 0 && (o.s.p - r.s.p) / se > 1.96; };
    // Rank by position (1, 2, 3…); only identical rounded percentages share a rank.
    const spread = rows.map((r, idx) => ({ id: r.a.id, best: rows.findIndex(o => Math.round((o.s.p || 0) * 100) === Math.round((r.s.p || 0) * 100)) + 1 }));
    const count = c => E.evals.filter(ev => c.f(ev) && (gap ? common(ev) : ev.modes.includes(mode))).length;
    const head = `<thead><tr><th class="rank" title="Rank by pass rate in the selected mode and pillar. Equal rates share a rank. Neighbouring ranks are often within each other's ± margin.">Rank ⓘ</th><th class="row-label">Configuration<span class="subline">model · harness</span></th>${cols.map(c => `<th>${c.name}${c.color ? `<span class="pacc" style="background:${c.color}"></span>` : ""}</th>`).join("")}${gap ? "" : `<th class="metric">$ / pass</th><th class="metric">Tokens / run</th><th class="metric">Skill read<span class="subline">skills only</span></th>`}</tr></thead>`;
    const body = rows.map(({ a, s }) => {
      const sp = spread.find(x => x.id === a.id);
      const cells = cols.map(c => gap ? cellGap(a.id, c.f, `data-cell="${a.id}.${c.key}"`) : cellPR(stats(a.id, mode, c.f), `data-cell="${a.id}.${c.key}"`));
      const read = mode === "skills" ? `<td class="num"><b style="color:${s.read < .6 ? "var(--red)" : s.read < .8 ? "var(--amber)" : "inherit"}" title="Share of Skills runs that opened the skill (${Math.round(s.read * 100)}%). Below 80% it shows amber, below 60% red: the Skills score then mostly reflects the model without the skill.">${pct(s.read)}</b></td>` : `<td class="num muted" title="Only measured with skills">–</td>`;
      const extra = gap ? "" : `<td class="num"><b>${usd(s.costPerPass)}</b></td><td class="num"><b>${tok(s.tokMed)}</b></td>${read}`;
      return `<tr><td class="rank">${sp.best}</td><th scope="row" class="row-label"><span class="cfg-name">${esc(a.name)}</span><span class="cfg-sub">${harnessFor(a, mode)}</span></th>${cells.map(c => `<td>${c}</td>`).join("")}${extra}</tr>`;
    }).join("");
    return `<div class="table-shell"><div class="table-scroll" tabindex="0" role="region" aria-label="Ranking"><table class="board configs">${head}<tbody>${body}</tbody></table></div><div class="table-note"><span>Click a cell for its evals and runs${st.pillar !== "all" ? " · columns split the pillar by task type" : ""}</span><span>Ranked by pass rate · check the ± before reading a gap between neighbours · ${S.ci}</span></div></div>`;
  }

  // ---------- Lift view (after Vals AI) ----------
  function viewLift() {
    const nI = E.evals.filter(ev => ev.modes.includes("internet") && inPillar(ev)).length;
    const rows = E.agents.map(a => { const i = stats(a.id, "internet", inPillar), s = stats(a.id, "skills", inPillar); return { a, i, s, lift: s.p - i.p }; }).sort((x, y) => (y.s.p || 0) - (x.s.p || 0));
    const bar = (s, c, label) => `<div class="lbar"><span class="lk">${label}</span><span class="ltrack"><i style="width:${s.p * 100}%;background:${c}"></i><u style="left:${s.lo * 100}%;width:${(s.hi - s.lo) * 100}%"></u></span><span class="lv">${pct(s.p)}</span></div>`;
    return `<div class="table-shell"><div class="lift-head"><div><h3>Accuracy lift from skills</h3><p class="muted">Each row is the same agent with and without ethskills, on the same ${nI} evals. Bars are pass rates with ${S.ci} whiskers.</p></div><div class="legend"><span><i class="sw" style="background:var(--i)"></i>Without skills</span><span><i class="sw" style="background:var(--s)"></i>With skills</span></div></div>
      <div class="lift-scale lift7"><span></span><span class="ticks"><b>0</b><b>25</b><b>50</b><b>75</b><b>100</b></span><span>Lift<br><small>same evals</small></span></div>
      ${rows.map(r => `<div class="lift-row lift7"><button class="lname" data-cell="${r.a.id}.${st.pillar}"><b>${esc(r.a.name)}</b><span class="cfg-sub">${r.a.harness}</span></button><div class="lbars">${bar(r.i, "var(--i)", "w/o")}${bar(r.s, "var(--s)", "with")}</div><span class="lift ${r.lift >= 0 ? "pos" : "neg"}">${isNaN(r.lift) ? "–" : pp(r.lift)}</span></div>`).join("")}
      <div class="table-note"><span>Both bars use the same evals, so the lift is a like-for-like comparison.</span><span>Click a name for its runs</span></div></div>`;
  }

  function pillarTabs(f) {
    return `<nav class="ptabs" aria-label="Pillars">${[["all", "All pillars", E.evals.filter(f).length], ...E.pillars.map(p => [p.id, p.name, E.evals.filter(ev => ev.pillar === p.id && f(ev)).length])].map(([id, name, n]) => `<button data-pillar="${id}" aria-pressed="${st.pillar === id}"${id !== "all" ? ` style="--pc:var(--p-${id})"` : ""}><b>${name}</b><span>${n} evals</span></button>`).join("")}</nav>`;
  }

  // ---------- separate page: Pre-training (Vanilla) ----------
  function renderPretrain() {
    root.querySelector("#main").innerHTML = `<div class="page" style="max-width:none">
      <div class="crumbs"><a href="${boardHash()}">Results</a> / Pre-training knowledge</div>
      <div class="pagehead"><h1>Pre-training knowledge <span class="muted" style="font-weight:400;font-size:18px">· Vanilla</span></h1><a class="backbtn" href="${boardHash()}">← Back to agent results</a></div>
      ${pillarTabs(ev => ev.modes.includes("vanilla"))}
      ${pretrain()}
    </div>`;
  }
  function pretrain() {
    const evs = E.evals.filter(ev => ev.modes.includes("vanilla") && inPillar(ev));
    const head = `<p class="hint">What each <b>model</b> knows on its own: no internet, no skills, no agent loop. Every model runs on the same pi harness with tools off, so only the ${E.evals.filter(ev => ev.modes.includes("vanilla")).length} knowledge evals (Quiz and single-answer Scenario) run here. This is not an agent ranking; it tracks how pre-training evolves.</p>`;
    if (!evs.length) return `<section class="board-section">${head}<div class="table-shell" style="padding:16px"><p class="muted">No ${pillarName()} evals run without tools: every eval in this pillar needs an agent loop.</p></div></section>`;
    const cols = [{ key: "all", name: st.pillar === "all" ? "Overall" : pillarName(), f: inPillar }, ...(st.pillar === "all" ? E.pillars.map(p => ({ key: p.id, name: p.name, f: ev => ev.pillar === p.id, color: `var(--p-${p.id})` })) : [])];
    const rows = E.agents.map(a => ({ a, s: stats(a.id, "vanilla", inPillar) })).sort((x, y) => (y.s.p || 0) - (x.s.p || 0));
    const rank = rows.map(r => rows.findIndex(o => Math.round((o.s.p || 0) * 100) === Math.round((r.s.p || 0) * 100)) + 1);
    const nC = evs.length;
    const head2 = `<thead><tr><th class="rank">Rank</th><th class="row-label">Model<span class="subline">pi · tools off</span></th>${cols.map(c => `<th>${c.name}${c.color ? `<span class="pacc" style="background:${c.color}"></span>` : ""}${E.evals.filter(ev => ev.modes.includes("vanilla") && c.f(ev) && inPillar(ev)).length ? "" : '<span class="subline">no knowledge evals</span>'}</th>`).join("")}<th style="min-width:260px">Same evals as an agent<span class="subline">pre-training → without skills → with skills</span></th></tr></thead>`;
    const body = rows.map(({ a, s }, idx) => {
      const f = ev => common(ev) && inPillar(ev);
      const v = stats(a.id, "vanilla", f), i = stats(a.id, "internet", f), sk = stats(a.id, "skills", f);
      return `<tr><td class="rank">${rank[idx]}</td><th scope="row" class="row-label"><span class="cfg-name">${esc(a.name)}</span><span class="cfg-sub">${orgOf[a.id]}</span></th>${cols.map(c => { const n = E.evals.filter(ev => ev.modes.includes("vanilla") && c.f(ev) && inPillar(ev)).length; return `<td>${n ? cellPR(stats(a.id, "vanilla", ev => c.f(ev) && inPillar(ev)), `data-vcell="${a.id}.${c.key}"`) : '<span class="na">–</span>'}</td>`; }).join("")}<td><div class="gap2" style="cursor:default"><span class="t"><span><em class="lvv">V</em> ${Math.round(v.p * 100)} <em class="lv">I</em> ${Math.round(i.p * 100)} <em class="ls">S</em> ${Math.round(sk.p * 100)}</span><b class="${sk.p >= v.p ? "pos" : "neg"}">${pp(sk.p - v.p)}</b></span>${track([{ p: v.p, c: "var(--v)", l: "Pre-training" }, { p: i.p, c: "var(--i)", l: "Without skills" }, { p: sk.p, c: "var(--s)", l: "With skills" }])}<span class="n" ${nC < 5 ? 'style="color:var(--amber)"' : ""}>${nC < 5 ? "few shared evals, read with care" : ""}</span></div></td></tr>`;
    }).join("");
    return `<section class="board-section">${head}<div class="table-shell"><div class="table-scroll"><table class="board configs pre">${head2}<tbody>${body}</tbody></table></div><div class="table-note"><span>Rows are models, not agents · the right column compares the same evals, so it is like for like</span><span>Click a cell for its runs</span></div></div></section>`;
  }



  // ---------- Matrix view (after Terminal-Bench-Science) ----------
  function viewMatrix() {
    const mode = st.mode === "gap" ? "skills" : st.mode;
    const evs = E.evals.filter(ev => inPillar(ev) && ev.modes.includes(mode));
    // Fixed order (by With skills), so the same row stays in place when the mode changes
    const rows = E.agents.map(a => ({ a, s: stats(a.id, mode, inPillar), key: stats(a.id, "skills", inPillar).p })).sort((x, y) => (y.key || 0) - (x.key || 0));
    const cell = (a, ev) => {
      const rs = runsOf(ev, a.id, mode); if (!ev.results[a.id][mode]) return `<td class="mx na">–</td>`;
      if (!rs.length) return `<td class="mx"><span class="pending" style="font-size:9px">no run</span></td>`;
      const ok = rs.filter(r => !r.invalid), k = ok.filter(r => r.pass).length, f = k / ok.length;
      return `<td class="mx"><button class="mxc" data-evcell="${a.id}.${ev.id}" style="background:color-mix(in srgb, var(--green) ${Math.round(f * 78)}%, #ffffff08);color:${f > .55 ? "#0b1f15" : "var(--text)"}" title="${esc(a.name)} · ${esc(ev.title)}: ${k} of ${ok.length} runs">${k}/${ok.length}</button></td>`;
    };
    return `<div class="table-shell"><div class="mx-title">Task matrix · ${pillarName()} · ${modeName(mode)}</div><div class="table-scroll" tabindex="0"><table class="matrix ${evs.length > 18 ? "compact" : ""}"><thead><tr><th class="row-label mxh">Configuration<span class="subline">pass rate</span></th>${evs.map(ev => `<th class="rot"><a href="#/eval/${ev.id}" title="${esc(ev.title)}"><span>${esc(ev.id)}</span></a></th>`).join("")}</tr></thead><tbody>${rows.map(({ a, s }) => `<tr><th class="row-label"><span class="cfg-name">${esc(a.name)} <span class="muted" style="font-weight:400;font-size:11px">${harnessFor(a, mode)}</span></span><span class="mono" style="font-size:12px;color:${color(s.p)}">${pct(s.p)} <span class="muted">${pm(s)}</span></span></th>${evs.map(ev => cell(a, ev)).join("")}</tr>`).join("")}</tbody></table></div><div class="table-note"><span>Runs passed per eval. Click an eval name for its page, or a cell for its runs.</span><span>Brighter green = more runs passed</span></div></div>`;
  }

  // ---------- Pareto view ----------
  // Pareto after OpenHands / ARC Prize / Artificial Analysis:
  // x = average cost per run (or tokens / time), y = pass rate with whiskers, dashed frontier,
  // and in "Both" an arrow per agent from without skills to with skills.
  function viewPareto() {
    const W = 1200, H = 380, m = { l: 56, r: 150, t: 14, b: 44 };
    const AX = { cost: ["average cost per run (USD, log)", r => r.cost, v => "$" + (v < .01 ? v.toFixed(3) : v.toFixed(2))], tokens: ["average tokens per run (log)", r => r.tokens.input + r.tokens.output, v => tok(v)], time: ["average time per run (s, log)", r => r.durationSec, v => Math.round(v) + "s"] };
    const [xl, xf, xfmt] = AX[st.px];
    const point = (a, md) => { const s = stats(a, md, inPillar); const rs = E.evals.filter(ev => ev.modes.includes(md) && inPillar(ev)).flatMap(ev => runsOf(ev, a, md)).filter(r => !r.invalid); return { md, s, x: rs.length ? rs.reduce((t, r) => t + xf(r), 0) / rs.length : NaN }; };
    const modes = st.pset === "both" ? ["internet", "skills"] : [st.pset];
    const pts = E.agents.map(a => ({ a, ms: modes.map(md => point(a.id, md)).filter(o => o.s.n && isFinite(o.x) && o.x > 0) })).filter(p => p.ms.length);
    if (!pts.length) return `<p class="muted">No runs for this pillar.</p>`;
    const xs = pts.flatMap(p => p.ms.map(o => o.x)), x0 = Math.min(...xs) * .8, x1 = Math.max(...xs) * 1.25;
    // y axis fitted to the data range (like OpenHands), in 10-point steps
    const los = pts.flatMap(p => p.ms.map(o => o.s.lo)), his = pts.flatMap(p => p.ms.map(o => o.s.hi));
    const y0 = Math.max(0, Math.floor(Math.min(...los) * 10) / 10), y1 = Math.min(1, Math.ceil(Math.max(...his) * 10) / 10);
    const X = x => m.l + (Math.log(x) - Math.log(x0)) / (Math.log(x1) - Math.log(x0)) * (W - m.l - m.r), Y = y => m.t + (1 - (y - y0) / (y1 - y0)) * (H - m.t - m.b);
    const mcol = { internet: "var(--i)", skills: "var(--s)" };
    // Frontier on the with-skills points (or the mode shown): nothing cheaper does better.
    const fmode = modes[modes.length - 1];
    const fpts = pts.map(p => ({ p, o: p.ms.find(o => o.md === fmode) })).filter(x => x.o).sort((a, b) => a.o.x - b.o.x);
    const front = []; let best = -1; fpts.forEach(x => { if (x.o.s.p > best) { front.push(x); best = x.o.s.p; } });
    const onFront = new Set(front.map(x => x.p.a.id));
    let g = "";
    for (let y = y0; y <= y1 + 1e-9; y += .1) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(y)}" y2="${Y(y)}" stroke="#ffffff14"/><text x="${m.l - 8}" y="${Y(y) + 4}" text-anchor="end">${Math.round(y * 100)}%</text>`;
    const ticks = []; for (let e = Math.floor(Math.log10(x0)); e <= Math.ceil(Math.log10(x1)); e++) [1, 2, 5].forEach(k => { const t = k * Math.pow(10, e); if (t >= x0 && t <= x1) ticks.push(t); });
    ticks.forEach(t => g += `<line x1="${X(t)}" x2="${X(t)}" y1="${m.t}" y2="${H - m.b}" stroke="#ffffff10"/><text x="${X(t)}" y="${H - m.b + 16}" text-anchor="middle">${xfmt(t)}</text>`);
    g += `<text x="${(W - m.r + m.l) / 2}" y="${H - 6}" text-anchor="middle">${xl} · cheaper ←</text><text transform="translate(14 ${H / 2}) rotate(-90)" text-anchor="middle">pass rate · better ↑</text>`;
    g += `<polyline fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="5 4" points="${front.map(x => `${X(x.o.x)},${Y(x.o.s.p)}`).join(" ")}"/>`;
    const placed = [];
    pts.forEach(p => {
      const lab = true;
      let body = "";
      if (p.ms.length === 2) body += `<line x1="${X(p.ms[0].x)}" y1="${Y(p.ms[0].s.p)}" x2="${X(p.ms[1].x)}" y2="${Y(p.ms[1].s.p)}" stroke="#ffffff55" stroke-width="1.2" marker-end="url(#ar6)"/>`;
      p.ms.forEach(o => { body += `<line x1="${X(o.x)}" x2="${X(o.x)}" y1="${Y(o.s.lo)}" y2="${Y(o.s.hi)}" stroke="${mcol[o.md]}" opacity=".45"/><circle cx="${X(o.x)}" cy="${Y(o.s.p)}" r="5.5" fill="${o.md === "internet" && p.ms.length === 2 ? "var(--panel)" : mcol[o.md]}" stroke="${mcol[o.md]}" stroke-width="2"/>`; });
      const last = p.ms[p.ms.length - 1];
      // Label on the right; if it collides, on the left; if that collides too, shift it down.
      const px = X(last.x), py = Y(last.s.p) + 4, w = esc(p.a.name).length * 7.2 + 12;
      const hits = (x0, x1, y) => placed.some(q => x0 < q.x1 && x1 > q.x0 && Math.abs(q.y - y) < 13);
      let side = "r", y = py;
      if (hits(px + 9, px + 9 + w, py)) { if (!hits(px - 9 - w, px - 9, py)) side = "l"; else { while (hits(px + 9, px + 9 + w, y)) y += 13; } }
      const lx0 = side === "r" ? px + 9 : px - 9 - w;
      placed.push({ x0: lx0, x1: lx0 + w, y });
      const tip = p.ms.map(o => `${modeName(o.md)}: ${pct(o.s.p)} ${pm(o.s)} · ${xfmt(o.x)} per run`).join(" | ");
      body += `<text class="lab" x="${side === "r" ? px + 9 : px - 9}" y="${y}" text-anchor="${side === "r" ? "start" : "end"}">${esc(p.a.name)}</text><title>${esc(p.a.name)} · ${esc(p.a.harness)} — ${tip}</title>`;
      g += `<g class="ppt ${lab ? "front" : ""}">${body}</g>`;
    });
    const legend = `${st.pset === "both" ? `<span><i class="sw" style="background:transparent;border:2px solid var(--i)"></i>Without skills</span><span><i class="sw" style="background:var(--s)"></i>With skills</span><span>arrow: same agent, without → with skills</span>` : `<span><i class="sw" style="background:${mcol[st.pset]}"></i>${modeName(st.pset)}</span>`}<span><span style="color:var(--accent)">- - -</span> frontier (${modeName(fmode).toLowerCase()}): nothing cheaper does better</span>`;
    return `<div class="table-shell" style="padding:12px 14px"><div class="legend" style="margin-bottom:6px">${legend}</div><div class="table-scroll"><svg class="pareto6" viewBox="0 0 ${W} ${H}" width="100%" style="min-width:720px;display:block" role="img" aria-label="Pass rate versus ${xl}"><defs><marker id="ar6" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#ffffffaa"/></marker></defs>${g}</svg></div>
      <div class="table-note" style="margin:10px -14px -12px"><span>Up and to the left is better. Whiskers: ${S.ci} interval of the pass rate.</span><span>Frontier configurations: ${front.map(x => esc(x.p.a.name)).join(", ")}</span></div></div>`;
  }


  // ---------- Models view (Vanilla, after Artificial Analysis) ----------
  function viewModels() {
    const rows = E.agents.map(a => ({ a, s: stats(a.id, "vanilla", inPillar) })).filter(r => r.s.n).sort((x, y) => y.s.p - x.s.p);
    const nV = E.evals.filter(ev => ev.modes.includes("vanilla") && inPillar(ev)).length;
    if (!rows.length) return `<div class="table-shell" style="padding:18px"><p class="muted">No ${pillarName()} evals run in Vanilla: they all need tools or a chain. Pick another pillar.</p></div>`;
    const H = 220;
    return `<div class="table-shell" style="padding:16px 18px"><div class="lift-head" style="padding:0 0 10px"><div><h3>What the model knows on its own</h3><p class="muted">Vanilla: no internet, no skills, every model on the same pi harness with tools off. ${nV} ${pillarName() === "All pillars" ? "" : pillarName() + " "}evals.</p></div><div class="legend">${Object.entries(orgColor).map(([o, c]) => `<span><i class="sw" style="background:${c}"></i>${o}</span>`).join("")}</div></div>
      <div class="vbars">${rows.map(({ a, s }) => `<button class="vbar" data-cell="${a.id}.${st.pillar}" title="${s.k} of ${s.n} runs passed"><span class="vcol" style="height:${H}px"><i style="height:${s.p * H}px;background:${orgColor[orgOf[a.id]]}"><b>${Math.round(s.p * 100)}</b></i><u style="bottom:${s.lo * H}px;height:${(s.hi - s.lo) * H}px"></u></span><span class="vname">${esc(a.name)}</span><span class="vsub">${s.k}/${s.n} runs</span></button>`).join("")}</div>
      <div class="table-note" style="margin:12px -18px -16px"><span>Pass rate with ${S.ci} whiskers. Click a bar for its evals and runs.</span><span>Only Quiz and Scenario evals run without tools</span></div></div>`;
  }

  // ---------- example evals (after Artificial Analysis) ----------
  function examples() {
    const pick = ["calldata-sel-05", "audit-quiz-002", "dca-contract-01", "swap-calldata-01"].map(evalById).filter(Boolean);
    return `<section class="board-section"><div class="toolbar"><h2>Example evals</h2><a href="#/evals" class="muted">One per task type</a></div>${pick.map((ev, i) => { const sample = runsOf(ev, "opus", "skills")[0] || runsOf(ev, "opus", "internet")[0]; const p = E.pillars.find(x => x.id === ev.pillar); return `<details class="example"><summary><b>${esc(ev.title)}</b><span class="chipline"><span class="chip">${p.name}</span><span class="chip">${ev.type}</span><span class="chip">${ev.grader}</span></span><span class="muted mono" style="margin-left:auto;font-size:11px">${(() => { const rs = E.agents.flatMap(a => runsOf(ev, a.id, "skills")).filter(r => !r.invalid); return rs.length ? pct(rs.filter(r => r.pass).length / rs.length) + " of Skills runs pass" : ""; })()}</span></summary><div class="exbody"><p><b>Why it exists:</b> ${esc(ev.why)}</p><p><b>Task:</b> ${esc(ev.prompt)}</p><p><b>What the grader checks:</b></p><ul>${sample.checks.map(c => `<li>${esc(c.name)} <span class="muted mono" style="font-size:11px">· expects ${esc(c.expected)}</span></li>`).join("")}</ul><p><b>Deliverable:</b> <span class="mono">${sample.files.map(esc).join(", ")}</span> · <b>Modes:</b> ${ev.modes.map(modeName).join(", ")}</p><p><a href="#/eval/${ev.id}">Open the eval, its results and runs →</a></p></div></details>`; }).join("")}</section>`;
  }

  // ---------- board ----------
  function renderBoard() {
    const modeless = st.view === "lift";
    const mode = st.mode === "gap" ? "skills" : st.mode;
    const hint = st.view === "pareto" ? "Cost against quality: each agent at its average cost per run (like OpenHands, ARC Prize and Artificial Analysis). With both, the arrow shows what adding skills does to the same agent: up is better, left is cheaper."
      : st.view === "lift" ? "Lift compares each agent with and without ethskills on the same evals."
      : `Showing agents <b>${mode === "skills" ? "with" : "without"} skills</b> · ${mode === "skills" ? "internet + ethskills in .agents/skills" : "open web, no skills"}. Both run the same evals.`;
    document.getElementById("kpiwrap").innerHTML = kpis();
    root.querySelector("#main").innerHTML = `
      ${pillarTabs(ev => true)}
      <section class="board-section">
        <h2>${pillarName()} · agents · ${E.evals.filter(ev => ev.modes.includes("internet") && inPillar(ev)).length} evals</h2>
        <div class="toolbar">${segmented(VIEWS, st.view, "view")}${st.view === "pareto" ? segmented([["both", "Without → with skills"], ["skills", "With skills"], ["internet", "Without skills"]], st.pset, "pset") + segmented([["cost", "Cost / run"], ["tokens", "Tokens / run"], ["time", "Time / run"]], st.px, "px") : modeless ? "" : segmented([["internet", "Without skills"], ["skills", "With skills"]], st.mode, "mode")}<a class="backbtn compare-btn" href="#/compare">Compare configurations →</a></div>
        <p class="hint">${hint}</p>
        ${st.view === "ranking" ? viewRanking() : st.view === "lift" ? viewLift() : st.view === "matrix" ? viewMatrix() : st.view === "pareto" ? viewPareto() : viewModels()}
      </section>
      ${examples()}
      <details class="read"><summary>How to read this report</summary>
        <p>A run passes only if it meets every check of its eval. Each eval runs 3–5 times per configuration and mode. The number after ± is half the ${S.ci} interval; configurations whose intervals overlap share a rank range.</p>
        <p>The main board compares agents with and without skills on the same evals. Pre-training (Vanilla) is a separate section: models on the pi harness with tools blocked, only on knowledge evals. It is compared with the agent modes only on the evals both ran.</p>
        <p>Colors: green is 80% or more of runs passed, amber 50–79%, red under 50%; cell tint grows with the rate. "Skill read" under 60% is flagged: the Skills score then mostly measures the model.</p>
      </details>`;
  }

  // ---------- drawer ----------
  const dialog = () => document.getElementById("detail");
  function openDrawer(agentId, filter, label, override) {
    const a = agentById(agentId);
    const modes = override || (st.view === "lift" ? ["internet", "skills"] : [st.mode]);
    const evs = E.evals.filter(ev => filter(ev) && modes.some(m => ev.modes.includes(m)));
    const sm = modes.length > 1 ? "skills" : modes[0];
    const s = stats(agentId, sm, filter);
    const rows = evs.map(ev => `<div class="drow"><div><a class="title" href="#/eval/${ev.id}">${esc(ev.title)}</a><div class="meta">${ev.id} · ${ev.type} · ${ev.grader}${ev.released <= a.cutoff ? ' · <span style="color:var(--amber)">released before model cutoff</span>' : ""}</div></div><div style="display:grid;gap:4px;justify-items:end">${modes.filter(m => ev.modes.includes(m)).map(m => { const rs = runsOf(ev, agentId, m); const ok = rs.filter(r => !r.invalid); return `<span style="display:flex;gap:10px;align-items:center">${modes.length > 1 ? `<span class="mono muted" style="font-size:10px">${m[0].toUpperCase()}</span>` : ""}<span class="mono" style="font-size:12px;color:${color(ok.filter(r => r.pass).length / ok.length)}">${rs.length ? ok.filter(r => r.pass).length + "/" + ok.length : "no run yet"}</span><span class="dots">${rs.map(runDot).join("")}</span></span>`; }).join("")}</div></div>`).join("");
    document.getElementById("detail-content").innerHTML = `<header class="drawer-header"><div class="drawer-heading"><div class="drawer-caption">${esc(label)} · ${modes.length > 1 ? "all modes" : modeName(modes[0])}<br>${harnessFor(a, modes[0] === "vanilla" && modes.length === 1 ? "vanilla" : "skills")}</div><h2 id="detail-title">${esc(a.name)}</h2><div class="drawer-summary"><span class="mono">${s.k} of ${s.n} runs passed${modes.length > 1 ? " in Skills" : ""} · ${pct(s.p)} ${pm(s)}</span><span class="subline">Select a dot to open the run</span></div></div><button id="close-detail" class="close-button" aria-label="Close details">Close ×</button></header><div class="drawer-content"><div>${rows || '<p class="muted">No evals here.</p>'}</div></div>`;
    if (!dialog().open) dialog().showModal();
  }
  function openFromCell(cell) {
    const [a, key] = cell.split(".");
    if (!agentById(a)) return;
    const col = columnsForPillar().find(c => c.key === key);
    if (col) return openDrawer(a, ev => col.f(ev) && (st.mode !== "gap" || common(ev) || !E.evals.some(e => col.f(e) && common(e))), col.overall && st.pillar === "all" ? "All pillars" : col.name);
    if (key === "all" || E.pillars.some(p => p.id === key)) return openDrawer(a, ev => key === "all" || ev.pillar === key, key === "all" ? "All pillars" : E.pillars.find(p => p.id === key).name);
  }

  // ---------- Compare page (after Vals AI) ----------
  function renderCompare(list) {
    const ids = (list || "").split(",").filter(id => agentById(id)).slice(0, 5);
    if (!ids.length) { const top = E.agents.map(a => ({ a, s: stats(a.id, "skills") })).sort((x, y) => y.s.p - x.s.p).slice(0, 3).map(x => x.a.id); ids.push(...top); }
    const mode = st.cmpMode;
    const rowsDef = [
      ["Overall", a => stats(a, mode), "rate"],
      ...E.pillars.map(p => [p.name, a => stats(a, mode, ev => ev.pillar === p.id), "rate", `var(--p-${p.id})`]),
      ["Lift from skills (same evals)", a => ({ p: stats(a, "skills").p - stats(a, "internet").p }), "pp"],
      ["Skill read", a => ({ p: stats(a, "skills").read }), "readp"],
      ["Cost per passed run ↓", a => ({ p: stats(a, mode).costPerPass }), "usd"],
      ["Tokens per run ↓", a => ({ p: stats(a, mode).tokMed }), "tok"]
    ];
    const cmpPalette = ["#3ecf8e", "#60a5fa", "#f59e0b", "#a78bfa", "#f472b6"];
    const bestOf = (vals, kind) => { const xs = vals.map(v => v.p).filter(isFinite); if (!xs.length) return NaN; return kind === "usd" || kind === "tok" ? Math.min(...xs) : Math.max(...xs); };
    const fmt = (v, kind) => kind === "rate" ? `${pct(v.p)} <small class="muted">${pm(v)}</small>` : kind === "pp" ? (isNaN(v.p) ? "–" : pp(v.p)) : kind === "readp" ? pct(v.p) : kind === "usd" ? usd(v.p) : tok(v.p);
    const table = rowsDef.map(([name, fn, kind, pc]) => { const vals = ids.map(fn); const b = bestOf(vals, kind); return `<tr><th>${pc ? `<span class="sw" style="background:${pc}"></span>` : ""}${name}</th>${vals.map(v => `<td class="${v.p === b ? "best" : ""}">${fmt(v, kind)}</td>`).join("")}</tr>`; }).join("");
    const meta = [["Harness", a => `${a.harness} ${a.version}`], ["Vanilla harness", () => "pi 0.8.2 · tools off"], ["Effort", a => a.effort], ["Provider", a => orgOf[a.id]], ["Training cutoff", a => a.cutoff]];
    root.querySelector("#main").innerHTML = `<div class="page" style="max-width:none">
      <div class="crumbs"><a href="${boardHash()}">Results</a> / Compare</div>
      <div class="pagehead"><h1>Compare configurations</h1><a class="backbtn" href="${boardHash()}">← Back to results</a></div>
      <div class="pickrow"><span class="muted">Select up to 5:</span>${E.agents.map(a => `<button class="pick" data-pick="${a.id}" aria-pressed="${ids.includes(a.id)}">${ids.includes(a.id) ? "✓ " : ""}${esc(a.name)}</button>`).join("")}</div>
      <div class="toolbar">${segmented([["internet", "Without skills"], ["skills", "With skills"]], mode, "cmpmode")}<span class="muted">Best value in each row is highlighted · ↓ lower is better</span></div>
      <div class="table-shell"><div class="table-scroll"><table class="simple cmp"><thead><tr><th></th>${ids.map(id => `<th><span class="sw" style="background:${cmpPalette[ids.indexOf(id)]}"></span>${esc(agentById(id).name)}<span class="subline" style="display:block">${harnessFor(agentById(id), mode)}</span></th>`).join("")}</tr></thead><tbody>${table}</tbody></table></div></div>
      <h3>Pass rate by pillar</h3>
      <div class="table-shell" style="padding:14px 16px">${E.pillars.map(p => `<div class="cmpbars"><span>${p.name}</span><div>${ids.map((id, i) => { const s = stats(id, mode, ev => ev.pillar === p.id); return `<div class="lbar"><span class="lk" style="width:110px">${esc(agentById(id).name)}</span><span class="ltrack"><i style="width:${(s.p || 0) * 100}%;background:${cmpPalette[i]}"></i></span><span class="lv">${s.n ? pct(s.p) : "–"}</span></div>`; }).join("")}</div></div>`).join("")}</div>
      <h3>Pre-training knowledge <span class="muted" style="font-weight:400">· Vanilla, model only (pi, no tools), knowledge evals</span></h3>
      <div class="table-shell"><table class="simple cmp"><tbody>${[["Overall", () => true], ...E.pillars.map(p => [p.name, ev => ev.pillar === p.id])].map(([n, f]) => { const vals = ids.map(id => stats(id, "vanilla", f)); const best = Math.max(...vals.map(v => v.p).filter(isFinite)); return `<tr><th>${n}</th>${vals.map(v => `<td class="${v.p === best ? "best" : ""}">${v.n ? `${pct(v.p)} <small class="muted">${pm(v)}</small>` : '<span class="muted">no knowledge evals</span>'}</td>`).join("")}</tr>`; }).join("")}</tbody></table></div>
      <h3>Configuration details</h3>
      <div class="table-shell"><table class="simple cmp"><tbody>${meta.map(([n, f]) => `<tr><th>${n}</th>${ids.map(id => `<td>${esc(f(agentById(id)))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <div><a class="backbtn" href="${boardHash()}">← Back to results</a></div>
    </div>`;
    root.querySelectorAll("[data-pick]").forEach(b => b.onclick = () => { const id = b.dataset.pick; const next = ids.includes(id) ? ids.filter(x => x !== id) : ids.length < 5 ? [...ids, id] : ids; location.hash = "#/compare/" + next.join(","); });
    root.querySelectorAll("[data-cmpmode]").forEach(b => b.onclick = () => { st.cmpMode = b.dataset.cmpmode; renderCompare(ids.join(",")); });
  }


  // ---------- eval page ----------
  function renderEval(id) {
    const ev = evalById(id); if (!ev) return renderBoard();
    const p = E.pillars.find(x => x.id === ev.pillar);
    const sample = runsOf(ev, "opus", ev.modes[ev.modes.length - 1])[0] || { checks: [] };
    const rows = E.agents.map(a => `<tr><td><b>${esc(a.name)}</b> <span class="muted" style="font-size:11px">${a.harness}</span></td>${["internet", "skills", "vanilla"].map(id => E.modes.find(m => m.id === id)).map(m => { if (!ev.modes.includes(m.id)) return `<td class="muted ${m.id === "vanilla" ? "pre-col" : ""}">${m.id === "vanilla" ? "needs tools, not run" : "not run in this mode"}</td>`; const rs = runsOf(ev, a.id, m.id); if (!rs.length) return '<td><span class="pending">no run yet</span></td>'; const ok = rs.filter(r => !r.invalid); const k = ok.filter(r => r.pass).length; return `<td><span class="mono" style="color:${color(k / ok.length)}">${k}/${ok.length}</span> <span class="dots" style="margin-left:6px">${rs.map(runDot).join("")}</span></td>`; }).join("")}</tr>`).join("");
    const runs = E.agents.flatMap(a => ev.modes.flatMap(m => runsOf(ev, a.id, m).map(r => ({ r, a, m }))));
    root.querySelector("#main").innerHTML = `<div class="page">
      <div class="crumbs"><a href="${boardHash()}">Results</a> / ${p.name} / ${esc(ev.title)}</div>
      <div><h1>${esc(ev.title)}</h1><div class="eval-id" style="font-size:11px">${ev.id} · released ${ev.released}</div></div>
      <div class="chipline"><span class="chip">${p.name}</span><span class="chip">${ev.type}</span><span class="chip">grader: ${ev.grader}</span><span class="chip">modes: ${ev.modes.map(modeName).join(" · ")}</span></div>
      <div><h3>Why this eval exists</h3><p class="why" style="margin-top:6px">${esc(ev.why)}</p></div>
      <div><h3 style="margin-bottom:8px">Prompt</h3><pre>${esc(ev.prompt)}</pre></div>
      <div><h3 style="margin-bottom:8px">Checks</h3><p class="hint" style="margin-bottom:8px">A run passes only if it meets every check.</p><ol class="checks">${sample.checks.map(c => `<li>${esc(c.name)}${c.expected ? ` <span class="muted mono" style="font-size:11px">· expects ${esc(c.expected)}</span>` : ""}</li>`).join("")}</ol></div>
      <div><h3 style="margin-bottom:8px">Results by configuration</h3><div class="table-shell"><div class="table-scroll"><table class="simple"><thead><tr><th>Configuration</th><th>Without skills</th><th>With skills</th><th class="pre-col">Pre-training (Vanilla, pi)</th></tr></thead><tbody>${rows}</tbody></table></div></div></div>
      <details><summary style="cursor:pointer"><h3 style="display:inline">All runs (${runs.length})</h3> <span class="muted">· one row per run</span></summary><div class="table-shell" style="margin-top:8px"><div class="table-scroll"><table class="simple"><thead><tr><th>Run</th><th>Configuration</th><th>Mode</th><th>Result</th><th>Checks</th><th>Tokens</th><th>Time</th><th>Cost</th></tr></thead><tbody>${runs.map(({ r, a, m }) => `<tr><td><a href="#/run/${encodeURIComponent(r.id)}">run ${r.k}</a></td><td>${esc(a.name)}</td><td class="muted">${modeName(m)}${m === "skills" ? (r.skillRead ? " · skill read" : ' · <span style="color:var(--amber)">skill not read</span>') : ""}</td><td>${r.invalid ? '<span class="status invalid">INVALID</span>' : r.pass ? '<span class="positive">pass</span>' : `<span class="negative">${r.end === "done" ? "fail" : r.end}</span>`}</td><td><span class="dots">${r.checks.map(c => `<span class="dot ${c.ok ? "p" : "f"}" style="width:8px;height:8px"></span>`).join("")}</span></td><td class="mono">${tok(r.tokens.input + r.tokens.output)}</td><td class="mono">${r.durationSec}s</td><td class="mono">${usd(r.cost)}</td></tr>`).join("")}</tbody></table></div></div></details>
    </div>`;
  }

  // ---------- run page ----------
  function renderRun(id) {
    let run, ev, agent, mode;
    E.evals.forEach(e => E.agents.forEach(a => E.modes.forEach(m => runsOf(e, a.id, m.id).forEach(r => { if (r.id === id) { run = r; ev = e; agent = a; mode = m.id; } }))));
    if (!run) return renderBoard();
    const sibs = runsOf(ev, agent.id, mode), prev = sibs[run.k - 2], next = sibs[run.k];
    const st8 = run.invalid ? "invalid" : run.pass ? "pass" : "fail";
    const firstFail = run.checks.find(c => !c.ok);
    const tabs = ["Transcript", run.chain ? "Chain state" : ev.grader === "tests" ? "Files" : "Answer", "Raw"];
    root.querySelector("#main").innerHTML = `<div class="page">
      <div class="crumbs"><a href="${boardHash()}">Results</a> / <a href="#/eval/${ev.id}">${esc(ev.title)}</a> / run ${run.k} of ${run.n}</div>
      <div class="runhead"><span class="status ${st8}">${st8.toUpperCase()}</span><h1>${esc(ev.title)}</h1><span class="sib">${prev ? `<a href="#/run/${encodeURIComponent(prev.id)}" title="Previous run">‹</a>` : ""}run ${run.k} / ${run.n}${next ? `<a href="#/run/${encodeURIComponent(next.id)}" title="Next run">›</a>` : ""}</span></div>
      <div class="chipline"><span class="chip">${esc(agent.name)}</span><span class="chip">${harnessFor(agent, mode)}</span><span class="chip">${modeName(mode)}</span><span class="chip">${ev.type} · ${ev.grader}</span><span class="chip">${ev.id} · released ${ev.released}</span>${ev.released <= agent.cutoff ? '<span class="chip warn">eval released before model cutoff</span>' : ""}</div>
      ${run.invalid ? '<div class="banner"><b>Invalid run.</b> In Internet mode the agent fetched our own eval file (step 2). Kept for transparency, excluded from every score.</div>' : ""}
      ${mode === "skills" && !run.skillRead ? '<div class="banner">The skill was available but the agent <b>never read it</b> in this run. The result measures the model without the skill.</div>' : ""}
      <div class="tiles">
        <div class="tile"><div class="k">Checks</div><div class="val">${run.checks.filter(c => c.ok).length} / ${run.checks.length}</div></div>
        <div class="tile"><div class="k">Tokens</div><div class="val">${tok(run.tokens.input + run.tokens.output)}</div><div class="muted mono" style="font-size:10.5px">in ${tok(run.tokens.input - run.cached)} · cache ${tok(run.cached)} · out ${tok(run.tokens.output)}</div></div>
        <div class="tile"><div class="k">Cost</div><div class="val">${usd(run.cost)}</div></div>
        <div class="tile"><div class="k">Time</div><div class="val">${run.durationSec}s</div><div class="muted mono" style="font-size:10.5px">ended: ${run.end}</div></div>
        <div class="tile"><div class="k">${mode === "skills" ? "Skill" : "Network"}</div><div class="val">${mode === "skills" ? (run.skillRead ? "read" : "not read") : mode === "vanilla" ? "off" : "on"}</div></div>
      </div>
      <section class="verdict"><div class="vh"><h3>Grader verdict</h3><span class="muted mono" style="font-size:11px">${ev.grader}${ev.grader === "judge" ? " · blind judge" : ""}</span>${firstFail ? `<a href="#" data-step="${firstFail.step}" style="margin-left:auto;font:11px var(--mono);color:var(--accent)">Jump to first failure →</a>` : ""}</div>
        ${run.checks.map((c, j) => `<div class="ck"><span class="${c.ok ? "positive" : "negative"}">${c.ok ? "✓" : "✗"}</span><span>${j + 1}. ${esc(c.name)}</span><a href="#" data-step="${c.step}">step ${c.step}</a><div class="ex"><span>expected <b>${esc(c.expected)}</b></span><span>got <b class="${c.ok ? "" : "negative"}">${esc(c.got)}</b></span>${c.reason ? `<span>${esc(c.reason)}</span>` : ""}</div></div>`).join("")}
        ${run.grader.note ? `<div class="ck"><span></span><span class="muted">${esc(run.grader.note)}</span></div>` : ""}
      </section>
      <div class="page-tabs" role="tablist">${tabs.map((t, i) => `<button data-tab5="${t}" aria-pressed="${i === 0}">${t}</button>`).join("")}</div>
      <div id="tabbody"></div>
      <p class="muted mono" style="font-size:11px">Reproduce: npx ethevals run --eval ${ev.id} --harness ${mode === "vanilla" ? "pi" : agent.harness.toLowerCase().replace(/ /g, "-")} --model ${agent.id} --mode ${mode} --seed ${run.k}</p>
    </div>`;
    const tab = name => {
      document.querySelectorAll("[data-tab5]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.tab5 === name)));
      const body = document.getElementById("tabbody");
      if (name === "Transcript") body.innerHTML = run.steps.map((s, i) => `<div class="step ${s.flagged ? "flag" : ""}" id="step-${i + 1}"><span class="no">#${i + 1}</span><div><span class="kind ${s.kind}">${s.kind}</span>${s.flagged ? '<span class="status invalid" style="font-size:10px">our repo</span>' : ""}<pre>${esc(s.text)}</pre></div></div>`).join("");
      else if (name === "Chain state") body.innerHTML = `<p class="hint" style="margin-bottom:8px">Read from the local fork after the agent stopped.</p><div class="table-shell"><table class="simple"><thead><tr><th>Read</th><th>Before</th><th>After</th><th>Check</th></tr></thead><tbody>${run.chain.map(r => `<tr><td class="mono">${r[0]}</td><td class="mono">${r[1]}</td><td class="mono">${r[2]}</td><td class="${r[3] ? "positive" : "negative"}">${r[3] ? "✓" : "✗"}</td></tr>`).join("")}</tbody></table></div>`;
      else if (name === "Answer") body.innerHTML = `<div class="table-shell"><table class="simple"><tbody><tr><td class="muted">Grader</td><td>${ev.grader === "judge" ? "Blind judge against the rubric (criteria in the verdict above)" : "Exact match after trimming and lower-casing"}</td></tr><tr><td class="muted">Expected</td><td class="mono">${esc(run.checks[0].expected)}</td></tr><tr><td class="muted">Given</td><td class="mono ${run.checks[0].ok ? "" : "negative"}">${esc(run.checks[0].got)}</td></tr></tbody></table></div><pre style="margin-top:10px">${esc(run.diff)}</pre>`;
      else if (name === "Files") body.innerHTML = `<div class="file-list" style="margin-bottom:8px">${run.files.map(esc).join("<br>")}</div><pre>${run.diff.split("\n").map(l => `<span class="${l.startsWith("+") ? "positive" : l.startsWith("-") ? "negative" : ""}">${esc(l)}</span>`).join("\n")}</pre>`;
      else body.innerHTML = `<pre>${esc(JSON.stringify({ id: run.id, pass: run.pass, score: run.score, checks: run.checks, tokens: run.tokens, cost: run.cost, durationSec: run.durationSec }, null, 2))}</pre>`;
    };
    document.querySelectorAll("[data-tab5]").forEach(b => b.onclick = () => tab(b.dataset.tab5));
    document.querySelectorAll("[data-step]").forEach(a => a.onclick = e => { e.preventDefault(); tab("Transcript"); const el = document.getElementById("step-" + a.dataset.step); if (el) { document.querySelectorAll(".step.hl").forEach(x => x.classList.remove("hl")); el.classList.add("hl"); el.scrollIntoView({ block: "center" }); } });
    tab("Transcript");
  }

  // ---------- shell ----------
  root.innerHTML = `<nav class="topnav" aria-label="Prototype views"><a class="brand" href="../index.html">ETH Evals <span class="muted">/ prototypes</span></a><a href="../index.html">Index</a><a href="../1/index.html">1 <span>Mode tabs</span></a><a href="../2/index.html">2 <span>Split columns</span></a><a href="../3/index.html">3 <span>Grouped modes</span></a><a href="../4/index.html">4 <span>Skills toggle</span></a><a href="index.html" aria-current="page">5 <span>Report</span></a></nav>
    <main><header class="hero6"><div class="hero-l"><p class="eyebrow">${E.evals.length} evals · 4 pillars · ${E.agents.length} configurations · 3 modes · ${E.evals.reduce((n, ev) => n + E.agents.reduce((m, a) => m + E.modes.reduce((k, md) => k + runsOf(ev, a.id, md.id).length, 0), 0), 0).toLocaleString("en")} runs</p><h1>How well do AI agents handle Ethereum?</h1><p class="prov6">suite ${S.version} · ${S.hash} · data ${S.date} · prototype 5, fake results</p></div><div class="hero-r" id="kpiwrap"></div></header>
    <div id="main" style="display:grid;gap:22px"></div>
    <section class="table-shell" style="padding:14px 16px;display:grid;gap:6px"><h3>Run it on your AI</h3><p class="muted">Run the same suite with your own harness, model or skills and submit the results file with a pull request. Community results show up with a badge.</p><pre>npx ethevals run --harness &lt;yours&gt; --model &lt;yours&gt; --modes vanilla,internet,skills --runs 5</pre></section>
    <p class="footer-note">Synthetic data built on the PR #2 dataset. <span class="canary">${S.canary}</span></p></main>
    <dialog id="detail" aria-labelledby="detail-title"><div id="detail-content"></div></dialog>`;

  // Changing pillar, view or mode does not navigate: it redraws in place and keeps scroll and focus.
  function updateBoard(btn) {
    st.cell = "";
    const key = btn.dataset.view ? `[data-view="${st.view}"]` : btn.dataset.mode ? `[data-mode="${st.mode}"]` : btn.dataset.base ? `[data-base="${st.base}"]` : btn.dataset.pset ? `[data-pset="${st.pset}"]` : btn.dataset.px ? `[data-px="${st.px}"]` : `[data-pillar="${st.pillar}"]`;
    const y = window.scrollY;
    history.replaceState(null, "", boardHash());
    renderBoard();
    window.scrollTo(0, y);
    root.querySelector(key)?.focus({ preventScroll: true });
  }
  let lastRoute = null;
  function route() {
    if (dialog().open) dialog().close();
    const { route } = readHash();
    const kind = route[0] || "board";
    if (kind !== "board") document.getElementById("kpiwrap").innerHTML = "";
    if (route[0] === "eval") renderEval(decodeURIComponent(route[1] || ""));
    else if (route[0] === "run") renderRun(decodeURIComponent(route.slice(1).join("/")));
    else if (route[0] === "compare") renderCompare(decodeURIComponent(route[1] || ""));
    else if (route[0] === "pretraining") { if (["all", ...E.pillars.map(p => p.id)].includes(route[1])) st.pillar = route[1]; renderPretrain(); }
    else if (route[0] === "evals") { st.view = "matrix"; location.hash = boardHash(); return; }
    else { renderBoard(); if (st.cell) openFromCell(st.cell); }
    const here = kind + "/" + (route[1] || "");
    if (here !== lastRoute) window.scrollTo(0, 0);
    lastRoute = here;
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.id === "close-detail") dialog().close();
    else if (b.dataset.view) { st.view = b.dataset.view; updateBoard(b); }
    else if (b.dataset.mode) { st.mode = b.dataset.mode; updateBoard(b); }
    else if (b.dataset.pillar && location.hash.startsWith("#/pretraining")) { st.pillar = b.dataset.pillar; const y = scrollY; history.replaceState(null, "", "#/pretraining/" + st.pillar); renderPretrain(); scrollTo(0, y); }
    else if (b.dataset.pillar) { st.pillar = b.dataset.pillar; updateBoard(b); }
    else if (b.dataset.base) { st.base = b.dataset.base; updateBoard(b); }
    else if (b.dataset.pset) { st.pset = b.dataset.pset; updateBoard(b); }
    else if (b.dataset.px) { st.px = b.dataset.px; updateBoard(b); }
    else if (b.dataset.cell) { st.cell = b.dataset.cell; history.replaceState(null, "", boardHash()); openFromCell(b.dataset.cell); }
    else if (b.dataset.vcell) { const [a, key] = b.dataset.vcell.split("."); openDrawer(a, ev => (key === "all" || ev.pillar === key) && inPillar(ev), "Pre-training · " + (key === "all" ? pillarName() : E.pillars.find(p => p.id === key).name), ["vanilla"]); }
    else if (b.dataset.evcell) { const [a, evId] = b.dataset.evcell.split("."); const ev = evalById(evId); openDrawer(a, x => x.id === evId, ev.title); }
  });
  dialog().addEventListener("click", e => { if (e.target === dialog()) dialog().close(); });
  dialog().addEventListener("close", () => { if (st.cell && !location.hash.startsWith("#/")) { st.cell = ""; history.replaceState(null, "", boardHash()); } });
  dialog().addEventListener("click", e => { if (e.target.closest("a[href^='#/']")) { st.cell = ""; dialog().close(); } });
  addEventListener("hashchange", route);
  route();
})();
