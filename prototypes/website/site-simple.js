/* ETH Evals · website prototype, simplified Results.
   Built from site.js: same data, drawer, eval, run and compare pages. What changes:
   - Results is findings plus two tables (agents, bare models, ADR 0001), with no page-wide filters or mode switches.
     Without skills, with skills and the lift sit on one row; the only control is sorting by a column.
   - The lift chart, the Pareto chart, the header KPIs and the section bar are gone. Cost is one column ($ per pass);
     cost per run, tokens and time are in the panel that opens from a cell.
   - The eval-by-eval matrix moves to the Evals page, with its own mode switch.
   - A score is the mean of its evals' pass rates, so every eval weighs the same, as on the live board. */
(function () {
  "use strict";
  const E = window.EVALS, S = E.suite;
  const root = document.getElementById("app");
  const esc = v => String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = x => isNaN(x) ? "–" : Math.round(x * 100) + "%";
  // v1 shows one number per result: the 95% interval is still computed, but not shown.
  const pm = () => "";
  const pp = x => (x >= 0 ? "+" : "−") + Math.abs(Math.round(x * 100)) + "pp";
  const usd = x => isNaN(x) ? "–" : x < .01 ? "$" + x.toFixed(4) : "$" + x.toFixed(3);
  const tok = x => isNaN(x) ? "–" : x >= 1000 ? Math.round(x / 1000) + "k" : Math.round(x) + "";
  const color = p => isNaN(p) ? "var(--muted)" : p >= .8 ? "var(--green)" : p >= .5 ? "var(--amber)" : "var(--red)";
  const modeName = id => ({ vanilla: "Model only", internet: "Internet", skills: "Internet + Skills" })[id];
  const agentById = id => E.agents.find(a => a.id === id);
  const evalById = id => E.evals.find(e => e.id === id);
  const harnessFor = (a, mode) => mode === "vanilla" ? "API call · no tools · web search off" : `${a.harness} ${a.version} · ${a.effort}`;

  // ---------- stats ----------
  function wilson(k, n, z = 1.96) {
    if (!n) return { p: NaN, lo: NaN, hi: NaN, k, n };
    const p = k / n, d = 1 + z * z / n, c = p + z * z / (2 * n), m = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n));
    return { p, lo: (c - m) / d, hi: (c + m) / d, k, n };
  }
  const runsOf = (ev, agent, mode) => { const r = ev.results[agent][mode]; return r ? r.runs : []; };
  const validRuns = (ev, agent, mode) => runsOf(ev, agent, mode).filter(r => !r.invalid);
  const median = xs => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : NaN; };
  // A score is the mean of the per-eval pass rates, so every eval weighs the same.
  // se is how far that mean moves on a rerun of the same evals; each eval's rate is smoothed so 0/4 and 4/4
  // don't count as certain. lo and hi (95%) are for the range bars, not the cells.
  function stats(agent, mode, evFilter) {
    const evs = E.evals.filter(ev => ev.modes.includes(mode) && (!evFilter || evFilter(ev)));
    const all = evs.flatMap(ev => runsOf(ev, agent, mode));
    const rs = all.filter(r => !r.invalid);
    const k = rs.filter(r => r.pass).length;
    const per = evs.map(ev => validRuns(ev, agent, mode)).filter(x => x.length).map(x => ({ k: x.filter(r => r.pass).length, n: x.length }));
    const p = per.length ? per.reduce((s, e) => s + e.k / e.n, 0) / per.length : NaN;
    const se = per.length ? Math.sqrt(per.reduce((s, e) => { const q = (e.k + 1) / (e.n + 2); return s + q * (1 - q) / e.n; }, 0)) / per.length : NaN;
    const cost = rs.reduce((s, r) => s + r.cost, 0);
    return { p, se, lo: Math.max(0, p - 1.96 * se), hi: Math.min(1, p + 1.96 * se), k, n: rs.length, evals: evs.length, ran: per.length,
      // Below three passed runs the cost of a pass is mostly noise, so it is not shown.
      costPerPass: k >= 3 ? cost / k : NaN, costPerRun: rs.length ? cost / rs.length : NaN,
      tokMed: median(rs.map(r => r.tokens.input + r.tokens.output)), timeMed: median(rs.map(r => r.durationSec)),
      read: mode === "skills" && rs.length ? rs.filter(r => r.skillRead).length / rs.length : NaN,
      invalid: all.length - rs.length };
  }
  const common = ev => ev.modes.length === 3;

  function segmented(items, selected, key) {
    return `<div class="segmented" role="group">${items.map(([id, t]) => `<button data-${key}="${id}" aria-pressed="${id === selected}">${t}</button>`).join("")}</div>`;
  }

  // ---------- provider colours ----------
  const orgOf = { opus: "Anthropic", fable: "Anthropic", sonnet: "Anthropic", astra: "OpenAI", glm: "Z.ai", kimi: "Moonshot", deepseek: "DeepSeek" };

  // ---------- view state ----------
  // tv: the mode shown on the results page, by the leaderboard and the eval matrix alike. sort: the leaderboard column.
  const st = { tv: "skills", sort: "all", pillar: "all", evView: "list" };
  const boardHash = () => reportHash();
  const inPillar = ev => st.pillar === "all" || ev.pillar === st.pillar;
  const pillarName = () => st.pillar === "all" ? "All pillars" : E.pillars.find(p => p.id === st.pillar).name;

  // ---------- cells ----------
  // One number per cell: the tint carries the level; runs and evals are in the tooltip, one short fact per line.
  // open is "agent~mode~scope" for the panel.
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const TIP_NL = "&#10;";
  const rangeTip = s => [`${s.k} of ${s.n} runs passed · ${plural(s.ran, "eval")}`,
    s.ran < s.evals ? `${plural(s.evals - s.ran, "eval")} not run yet, left out` : "",
    s.invalid ? `${plural(s.invalid, "invalid run")} left out` : ""].filter(Boolean).join(TIP_NL);
  // Marked only when over a tenth of the evals have no runs; smaller gaps stay in the tooltip and the panel.
  const gappy = s => s.n > 0 && s.ran < .9 * s.evals;
  function cell(s, open) {
    if (!s.n) return `<span class="na" title="No runs">–</span>`;
    return `<button class="pr" data-open="${open}" style="--p:${s.p.toFixed(3)}" title="${rangeTip(s)}"><span class="v">${pct(s.p)}${gappy(s) ? `<sup class="few">*</sup>` : ""}</span></button>`;
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




  // ---------- results table: one table, three views ----------
  // Without skills and With skills are two views of the same agents on the same evals. With skills shows,
  // beside each score, the change over the same agent without skills, counted only on the evals that ran
  // in both modes (paired, like for like). Model only (closed-book) is a separate view: it runs a different,
  // smaller eval set, so it is not shown as a third series beside the other two.
  const SCOPES = () => [["all", () => true], ...E.pillars.map(p => [p.id, ev => ev.pillar === p.id])];
  function agentRows() {
    return E.agents.map(a => {
      const sc = {};
      SCOPES().forEach(([key, f]) => {
        const both = ev => f(ev) && validRuns(ev, a.id, "internet").length > 0 && validRuns(ev, a.id, "skills").length > 0;
        const pi = stats(a.id, "internet", both), ps = stats(a.id, "skills", both);
        sc[key] = { i: stats(a.id, "internet", f), s: stats(a.id, "skills", f), v: stats(a.id, "vanilla", f), pi, ps, lift: ps.p - pi.p, liftSe: Math.sqrt(pi.se ** 2 + ps.se ** 2) };
      });
      const t = sc.all;
      return { a, sc, i: t.i, s: t.s, v: t.v, pi: t.pi, ps: t.ps, lift: t.lift, liftSe: t.liftSe, pillars: E.pillars.map(p => sc[p.id].s) };
    });
  }
  // A lift is clear when it is larger than what a rerun could move it.
  const liftClear = x => Math.abs(x.lift) > 1.96 * x.liftSe;
  const MK = { internet: "i", skills: "s", vanilla: "v" };
  const lowFirst = key => key === "cost";
  const sortVal = (key, m) => key === "cost" ? r => r.sc.all[MK[m]].costPerPass : key === "read" ? r => r.s.read : r => (r.sc[key] || r.sc.all)[MK[m]].p;
  const nEvals = (m, key) => E.evals.filter(ev => ev.modes.includes(m) && (key === "all" || ev.pillar === key)).length;
  function viewSel() {
    const b = (id, t) => `<button data-tv="${id}" aria-pressed="${st.tv === id}">${t}</button>`;
    return `<div class="tvsel" role="group" aria-label="Which results"><div class="segmented">${b("internet", "Internet")}${b("skills", "Internet + Skills")}</div><span class="tvsep" aria-hidden="true"></span><div class="segmented tv-alt">${b("vanilla", "Model only")}</div></div>`;
  }
  // A score cell; in the With skills view it carries the paired change over the same agent without skills.
  function scoreCell(r, key, m) {
    const x = r.sc[key], s8 = x[MK[m]], open = `${r.a.id}~${m}~${key}`;
    if (!s8.n) return m === "vanilla" && !nEvals("vanilla", key) ? `<span class="na" title="No Model only evals in this pillar">–</span>` : `<span class="na" title="No runs">–</span>`;
    let lift = "";
    if (m === "skills" && isFinite(x.lift)) {
      const clear = liftClear(x);
      lift = `<span class="lft ${!clear ? "faint" : x.lift >= 0 ? "pos" : "neg"}">${Math.round(x.lift * 100) === 0 ? "0pp" : pp(x.lift)}</span>`;
    }
    const liftTip = m === "skills" && isFinite(x.lift) ? `${TIP_NL}${TIP_NL}Skills vs Internet: ${pct(x.pi.p)} → ${pct(x.ps.p)}${x.ps.ran < s8.ran ? ` (on the ${plural(x.ps.ran, "eval")} both ran)` : ""}${liftClear(x) ? "" : `${TIP_NL}Too small to rule out noise`}` : "";
    return `<button class="pr" data-open="${open}" style="--p:${s8.p.toFixed(3)}" title="${rangeTip(s8)}${liftTip}"><span class="v">${pct(s8.p)}${gappy(s8) ? `<sup class="few">*</sup>` : ""}</span>${lift}</button>`;
  }
  function resultsTable(rows) {
    const m = st.tv, vanilla = m === "vanilla";
    const key = st.sort === "read" && m !== "skills" ? "all" : vanilla && st.sort === "cost" ? "all" : st.sort;
    const val = sortVal(key, m), dir = lowFirst(key) ? 1 : -1;
    // rows without a value go last, whatever the direction
    const sorted = [...rows].sort((x, y) => isFinite(val(x)) && isFinite(val(y)) ? dir * (val(x) - val(y)) : isFinite(val(y)) - isFinite(val(x)));
    const noise = Math.round(median(rows.filter(r => r.sc.all[MK[m]].n).map(r => 1.96 * Math.SQRT2 * r.sc.all[MK[m]].se)) * 100);
    const th = (k, label, sub) => `<th aria-sort="${key === k ? (lowFirst(k) ? "ascending" : "descending") : "none"}"><button class="sortb" data-sort="${k}" title="Sort by this column">${label}${key === k ? `<span class="sarr">${lowFirst(k) ? "▲" : "▼"}</span>` : ""}</button>${sub ? `<span class="subline">${sub}</span>` : ""}</th>`;
    const cols = [["all", "Overall"], ...E.pillars.map(p => [p.id, p.name])];
    const withRead = m === "skills";
    // Fixed column widths and a table box that hugs them: Internet and Internet + Skills keep every column
    // in the same place, and Skill read is simply added on the right.
    const head = `<colgroup><col class="c-name">${cols.map(() => '<col class="c-score">').join("")}${vanilla ? "" : '<col class="c-num">'}${withRead ? '<col class="c-num">' : ""}</colgroup><thead><tr><th class="row-label">${vanilla ? "Model" : "Configuration"}<span class="subline">${vanilla ? "API call · no tools" : "model · harness"}</span></th>${cols.map(([k, l]) => th(k, l, vanilla && !nEvals("vanilla", k) ? "no Model only evals" : "")).join("")}${vanilla ? "" : th("cost", "$ / pass")}${withRead ? th("read", "Skill read") : ""}</tr></thead>`;
    const body = sorted.map(r => {
      const { a } = r, t = r.sc.all[MK[m]];
      const cost = vanilla ? "" : `<td class="num" title="${isFinite(t.costPerPass) ? `${usd(t.costPerRun)} per run on average · median ${tok(t.tokMed)} tokens and ${t.timeMed}s per run` : "Fewer than three passed runs: too few to price a pass"}"><b>${usd(t.costPerPass)}</b></td>`;
      const read = !withRead ? "" : `<td class="num"><b style="color:${r.s.read < .6 ? "var(--red)" : r.s.read < .8 ? "var(--amber)" : "inherit"}" title="Share of runs in which the agent opened the skill.">${pct(r.s.read)}</b></td>`;
      return `<tr><th scope="row" class="row-label"><span class="cfg-name">${esc(a.name)}</span><span class="cfg-sub">${vanilla ? orgOf[a.id] : harnessFor(a, "skills")}</span></th>${cols.map(([k]) => `<td>${scoreCell(r, k, m)}</td>`).join("")}${cost}${read}</tr>`;
    }).join("");
    const anyGap = rows.some(r => cols.some(([k]) => gappy(r.sc[k][MK[m]])));
    const anyFaint = m === "skills" && rows.some(r => cols.some(([k]) => isFinite(r.sc[k].lift) && !liftClear(r.sc[k])));
    const notes = ["Click a score for its evals and runs", m === "skills" ? '<b class="lft-key">+pp</b> change over Internet' : "", anyGap ? "* some evals not run yet" : ""].filter(Boolean).join(" · ");
    return `<div class="table-shell fit"><div class="table-scroll" tabindex="0" role="region" aria-label="Results"><table class="board configs lean${vanilla ? " models" : ""}">${head}<tbody>${body}</tbody></table></div><div class="table-note"><span>${notes}</span></div></div>`;
  }
  const modelOnlyNote = () => { const nV = nEvals("vanilla", "all"); return `<div class="tvnote"><p><b>Model only.</b> Each model is called directly through its API, with no tools and web search off. Only the ${nV} evals with a checkable answer run this way, so these scores are <b>not comparable</b> with Internet and Internet + Skills.</p></div>`; };

  // Only Model only needs a note: its scores cover a different eval set.
  function viewIntro() {
    if (st.tv === "vanilla") return modelOnlyNote();
    return "";
  }

  // ---------- Matrix view (after Terminal-Bench-Science) ----------
  function viewMatrix() {
    const mode = st.tv;
    const evs = E.evals.filter(ev => ev.modes.includes(mode));
    // Fixed order (by Internet + Skills), so the same row stays in place when the mode changes
    const rows = E.agents.map(a => ({ a, key: stats(a.id, "skills").p })).sort((x, y) => (y.key || 0) - (x.key || 0));
    const groups = E.pillars.map(p => ({ p, evs: evs.filter(ev => ev.pillar === p.id) })).filter(g => g.evs.length);
    const first = new Set(groups.map(g => g.evs[0].id));
    const cell = (a, ev) => {
      const g = first.has(ev.id) ? " gstart" : "";
      const rs = runsOf(ev, a.id, mode); if (!ev.results[a.id][mode]) return `<td class="mx na${g}">–</td>`;
      if (!rs.length) return `<td class="mx${g}"><span class="pending" style="font-size:9px">no run</span></td>`;
      const ok = rs.filter(r => !r.invalid), k = ok.filter(r => r.pass).length, f = k / ok.length;
      return `<td class="mx${g}"><button class="mxc" data-evcell="${a.id}.${ev.id}" style="--p:${f.toFixed(3)};background:color-mix(in srgb, var(--green) ${Math.round(f * 78)}%, #ffffff08);color:${f > .55 ? "#0b1f15" : "var(--text)"}" title="${esc(a.name)} · ${esc(ev.title)}: ${k} of ${ok.length} runs">${k}/${ok.length}</button></td>`;
    };
    const band = groups.map((g, i) => `<th class="mxp mxp-${i % 2} gstart" colspan="${g.evs.length}">${g.p.name}</th>`).join("");
    const names = evs.map(ev => `<th class="rot${first.has(ev.id) ? " gstart" : ""}"><a href="#/eval/${ev.id}" title="${esc(ev.title)}"><span>${esc(ev.id)}</span></a></th>`).join("");
    return `<div class="table-shell"><div class="mx-title">Eval matrix · ${modeName(mode)}</div><div class="table-scroll" tabindex="0"><table class="matrix grouped ${evs.length > 18 ? "compact" : ""}"><thead><tr><th class="row-label mxh" rowspan="2"></th>${band}</tr><tr>${names}</tr></thead><tbody>${rows.map(({ a }) => `<tr><th class="row-label"><span class="cfg-name">${esc(a.name)}</span><span class="cfg-sub">${harnessFor(a, mode)}</span></th>${evs.map(ev => cell(a, ev)).join("")}</tr>`).join("")}</tbody></table></div><div class="table-note"><span>Runs passed per eval. Click an eval name for its page, or a cell for its runs.</span></div></div>`;
  }
  // Evals: one matrix. Agents (or models) are the columns, evals the rows grouped by pillar, named by title.
  // The agent views list every eval, with "–" where an eval does not run in that mode, so none disappears.
  // Model only lists just the evals that can run closed-book.
  function viewMatrix2() {
    const mode = st.tv, vanilla = mode === "vanilla";
    const evs = vanilla ? E.evals.filter(ev => ev.modes.includes("vanilla")) : E.evals;
    // Agent columns keep one order (by Internet + Skills) in both agent views; models are ordered by Model only.
    const agents = E.agents.map(a => ({ a, key: stats(a.id, vanilla ? "vanilla" : "skills").p })).sort((x, y) => (y.key || 0) - (x.key || 0)).map(x => x.a);
    const groups = E.pillars.map(p => ({ p, evs: evs.filter(ev => ev.pillar === p.id) })).filter(g => g.evs.length);
    const cell = (a, ev) => {
      const rs = runsOf(ev, a.id, mode); if (!ev.modes.includes(mode) || !ev.results[a.id][mode]) return `<td class="mx na" title="Not run in this mode">–</td>`;
      if (!rs.length) return `<td class="mx"><span class="pending" style="font-size:9px">no run</span></td>`;
      const ok = rs.filter(r => !r.invalid), k = ok.filter(r => r.pass).length, f = k / ok.length;
      return `<td class="mx"><button class="mxc" data-evcell="${a.id}.${ev.id}" style="--p:${f.toFixed(3)};background:color-mix(in srgb, var(--green) ${Math.round(f * 78)}%, #ffffff08);color:${f > .55 ? "#0b1f15" : "var(--text)"}" title="${esc(a.name)} · ${esc(ev.title)}: ${k} of ${ok.length} runs">${k}/${ok.length}</button></td>`;
    };
    const head = `<thead><tr><th class="row-label mxh"></th>${agents.map(a => `<th class="agh"><span class="cfg-name">${esc(a.name)}</span><span class="cfg-sub">${vanilla ? orgOf[a.id] : harnessFor(a, mode)}</span></th>`).join("")}</tr></thead>`;
    const meta = ev => `${ev.type} · ${((SCORER[ev.grader] || [ev.grader])[0]).toLowerCase()}`;
    const body = groups.map((g, i) => `<tr class="mxgrp"><th class="mxp mxp-${i % 2}" colspan="${agents.length + 1}"><span class="mxp-l">${g.p.name}</span></th></tr>${g.evs.map(ev => `<tr><th class="row-label evl"><a href="#/eval/${ev.id}">${esc(ev.title)}</a><span class="cid">${meta(ev)}</span></th>${agents.map(a => cell(a, ev)).join("")}</tr>`).join("")}`).join("");
    return `<div class="table-shell"><div class="mx-title">Eval matrix · ${vanilla ? "Model only" : modeName(mode)}</div><div class="table-scroll" tabindex="0"><table class="matrix t2">${head}<tbody>${body}</tbody></table></div><div class="table-note"><span>Runs passed per eval. Click an eval for its page, or a cell for its runs.</span></div></div>`;
  }




  // ---------- what we measure, how an eval runs, all evals ----------
  // Sources: issue #1 (pillars, modes), PR #4 (eval spec, CONTEXT.md, ADRs), PR #5 (system proposal).
  // Anything tagged "ours" is our own proposal to fill a gap: it is not in the repo yet.
  const SRC = { i1: ["Issue #1", "https://github.com/BuidlGuidl/ethevals/issues/1"], spec: ["PR #4 · eval spec", "https://github.com/BuidlGuidl/ethevals/pull/4"], prop: ["PR #5 · system proposal", "https://github.com/BuidlGuidl/ethevals/pull/5"] };
  const src = (...keys) => `<span class="srcs">${keys.map(k => k === "ours" ? `<span class="src ours" title="Not in the repo: our own proposal to fill a gap">Our proposal · not in the repo</span>` : `<a class="src" href="${SRC[k][1]}" target="_blank" rel="noopener">${SRC[k][0]}</a>`).join("")}</span>`;
  const PILLAR_INFO = {
    concepts: { q: "Does it understand how Ethereum works?", areas: [["Protocol", "finality, consensus, forks"], ["Gas and fees", "EIP-1559, blobs"], ["L2s", "rollups, withdrawals"], ["Standards", "ERCs and EIPs"], ["Wallets", "custody and keys"]] },
    transactions: { q: "Can it make things happen on chain?", areas: [["Encode", "selectors, calldata, signatures"], ["Read state", "pools, fees, balances"], ["Send", "transfers and swaps on a fork"]] },
    building: { q: "Can it ship contracts and frontends that work?", areas: [["Contracts", "from a spec to a tested contract"], ["Testing", "fuzz and invariant suites"], ["Repair", "fix a broken project"], ["Frontend", "wallet flows in the UI"]] },
    security: { q: "Can it find, explain and fix vulnerabilities?", areas: [["Patterns", "know the classic bugs"], ["Audit", "review and triage findings"], ["Exploit and patch", "prove the bug, then fix it"]] },
  };
  const AREA = { "concepts-k-06": "Protocol", "gas-basefee-01": "Gas and fees", "l2s-k-03": "L2s", "erc-8004-quiz": "Standards", "latest-eip-live": "Standards", "wallets-quiz-002": "Wallets", "l2s-quiz-002": "L2s",
    "calldata-sel-05": "Encode", "tx-calldata-permit-2612": "Encode", "live-pool-liquidity": "Read state", "proto-blob-base-fee": "Read state", "swap-calldata-01": "Send", "tx-eip1559-transfer": "Send",
    "erc20-oz": "Contracts", "dca-contract-01": "Contracts", "lp-rebalance-01": "Contracts", "repo-repair": "Repair", "testing-goal-001": "Testing", "frontend-ux-goal-002": "Frontend",
    "security-k-08": "Patterns", "audit-quiz-002": "Audit", "security-goal-001": "Audit", "vault-exploit-patch": "Exploit and patch", "dvd-puppet": "Exploit and patch", "fix-vault-01": "Exploit and patch" };
  const CHAIN = { "live-pool-liquidity": "mainnet fork, pinned", "proto-blob-base-fee": "mainnet fork, pinned", "swap-calldata-01": "mainnet fork, pinned", "lp-rebalance-01": "mainnet fork, pinned",
    "tx-eip1559-transfer": "fresh local chain", "dca-contract-01": "fresh local chain", "vault-exploit-patch": "local chain + setup/", "dvd-puppet": "local chain + setup/" };

  function measureSection(asLinks) {
    const byArea = (p, a) => E.evals.filter(ev => ev.pillar === p && AREA[ev.id] === a).length;
    const modes = [["vanilla", "Pre-training", "The bare model: the prompt only, no harness, no tools.", "what it learned in training", "Quizzes only · its own page"],
      ["internet", "Internet", "An agent (harness + model) with the web, a shell, its workspace and the eval's chain.", "whether it finds the right content when it looks", "Agent results"],
      ["skills", "Internet + Skills", "The same agent plus the Ethereum skills (ethskills).", "whether curated context fixes it", "Agent results"]];
    return `<section class="method" id="measure">
      <div class="mhead"><h2>What we measure</h2><p>How well AI agents handle Ethereum work, across four pillars, and what bare models know about it. Every eval is a task plus a grader that decides pass or fail. ${src("i1", "spec")}</p></div>
      <div class="pillars4">${E.pillars.map(p => { const info = PILLAR_INFO[p.id]; const n = E.evals.filter(ev => ev.pillar === p.id).length; return `<${asLinks ? `a href="#/evals?pillar=${p.id}"` : `button data-pillar="${p.id}" aria-pressed="${st.pillar === p.id}"`} class="pcard"><span class="pk">${p.name}<span>${n} evals</span></span><b>${info.q}</b><span class="areas">${info.areas.map(([a, d]) => `<span><em>${a}</em><span>${d}</span><i>${byArea(p.id, a)}</i></span>`).join("")}</span></${asLinks ? "a" : "button"}>`; }).join("")}</div>
      <div class="modes3">${modes.map(([id, n, what, gap, where]) => `<div class="mcard m-${id}"><span class="pk">${n}<span>${where}</span></span><p>${what}</p><p class="mgap">The gap tells us ${gap}.</p></div>`).join("")}</div>
      <p class="srcnote">Pillar questions and the three modes come from issue #1 and CONTEXT.md. The areas inside each pillar, and which eval measures which area, are ${src("ours")}</p>
    </section>`;
  }

  function filledBlock() {
    return `<div class="filled">
          <div class="ours"><h3>Pieces we filled in ${src("ours")}</h3><ul>
            <li>The areas inside each pillar and the eval → area mapping above.</li>
            <li>3–5 runs per eval. The spec only says "several runs".</li><li>Scores shown without an error bar, although the spec pairs every score with one.</li>
            <li>The chain each eval needs, in the Evals list. The spec defines the keys, not these values.</li>
            <li>Skill read: the share of Internet + Skills runs that opened the skill. PR #5 says Inspect's logs can show it; the metric is ours.</li>
            <li>A contamination flag when an eval was released before a model's training cutoff.</li>
          </ul></div>
          <div class="q"><h3>Open questions in the spec ${src("spec")}</h3><ul>
            <li>Are vanilla, internet and skills the right mode names?</li>
            <li>A canary string and release date per eval, and a private held-out set?</li>
            <li>Forks at the latest block and several chains in one eval are parked.</li>
            <li>The spec lets only quizzes run in vanilla; three Scenario evals in this prototype's data still do.</li>
          </ul></div>
        </div>`;
  }
  function howSection(full) {
    const steps = [
      ["Write an eval", `One folder per eval: <code>eval.yaml</code> (type, modes, motivation, prompt, chain), <code>starter/</code> with the agent's files, <code>setup/</code> to prepare the chain, and <code>grader/</code>. YAML, Markdown and Solidity tests, no Python. Anyone adds one by pull request.`, ["spec", "prop"]],
      ["Run it in isolation", `The runner, built on Inspect, starts fresh containers for every run: the agent, an anvil chain behind an RPC filter that blocks cheat methods, and a grader the agent can't reach. Only the prompt and <code>starter/</code> reach the agent.`, ["spec", "prop"]],
      ["Grade with named checks", `An exact answer, hidden Foundry tests, a script that reads the chain, or a rubric read by a judge model that is never the model under test. Each check is <code>{ name, pass, reason }</code>. A run passes only if every check passes.`, ["spec", "prop"]],
      ["Repeat and score", `Each eval runs several times per agent and mode. The score is the share of runs that passed. Every result stores a hash of the eval's files, so a changed eval never mixes with older results.`, ["spec"]],
      ["Publish", `Merging an eval, or adding a model, runs only what is missing, after a budget check. CI opens a results PR and the site updates on merge, with a transcript behind every result. On each release, the quiz rows go to the EF's Hugging Face dataset.`, ["prop"]],
    ];
    const graders = [["answer.txt", "Quiz", "The trimmed reply equals the answer. \"not 8004\" fails."], ["rubric.md", "any type", "A judge model answers each bullet pass or fail, with a reason."], ["tests/", "Build", "Hidden tests run against the agent's workspace. One test, one check."], ["check script", "Act", "Reads the chain after the run and returns checks."]];
    return `<section class="method" id="how">
      <div class="mhead"><h2>How an eval runs</h2><p>From a folder in the repo to a cell on this page. The system is still a proposal under review, so this is how it is meant to work. ${src("spec", "prop")}</p></div>
      <ol class="flow">${steps.map(([h, t, k]) => `<li class="fstep"><h3>${h}</h3><p>${t}</p>${src(...k)}</li>`).join("")}</ol>
      <div class="how2">
        <div class="table-shell"><table class="simple"><thead><tr><th>Grader file</th><th>Used by</th><th>What it checks</th></tr></thead><tbody>${graders.map(([f, u, w]) => `<tr><td class="mono">${f}</td><td>${u}</td><td class="muted">${w}</td></tr>`).join("")}</tbody></table><div class="table-note"><span>Grader kinds from the PR #4 spec. One eval can use several.</span></div></div>
        ${full === false ? "" : filledBlock()}
      </div>
    </section>`;
  }

  // Scorer kinds, in the repo's vocabulary (CONTEXT.md on main): a target the answer must match, Forge tests,
  // a check script that reads the chain or workspace, or a rubric that a grader model answers.
  const SCORER = { deterministic: ["Answer match", "automatic"], judge: ["Rubric", "grader model"], tests: ["Forge tests", "automatic"], "chain state": ["Check script", "automatic"] };
  const GRADER_FILE = Object.fromEntries(Object.entries(SCORER).map(([k, [n, how]]) => [k, how === "automatic" ? n.toLowerCase() : `${n.toLowerCase()} · ${how}`]));
  const MODE_TAG = { vanilla: "Model only", internet: "Internet", skills: "+ Skills" };
  function catalogSection() {
    const evs = E.evals;
    const count = t => evs.filter(ev => ev.type === t).length;
    const types = ["Quiz", "Scenario", "Build", "Act"].filter(count).map(t => `${count(t)} ${t.toLowerCase()}`).join(" · ");
    const row = ev => { const rs = E.agents.flatMap(a => runsOf(ev, a.id, "skills")).filter(r => !r.invalid); const pr = rs.length ? rs.filter(r => r.pass).length / rs.length : NaN; const [sb, how] = SCORER[ev.grader] || [ev.grader, ""];
      return `<tr><td class="ct"><a href="#/eval/${ev.id}">${esc(ev.title)}</a></td><td><span class="chip">${ev.type}</span></td><td class="csb"><b>${sb}</b><span>${how}</span></td><td class="cmodes">${["vanilla", "internet", "skills"].filter(m => ev.modes.includes(m)).map(m => `<span class="mtag m-${m}">${MODE_TAG[m]}</span>`).join("")}</td><td class="mono cc">${CHAIN[ev.id] || `<span class="muted" title="No chain">–</span>`}</td><td class="mono cpr">${isNaN(pr) ? "–" : pct(pr)}</td></tr>`; };
    return `<section class="board-section catalog" id="evals">
      <div class="toolbar"><h2>All evals</h2><span class="muted mono">${evs.length} evals · ${types}</span></div>
      <p class="hint">Every eval in the suite, grouped by pillar and by what it measures. Open one for its prompt, its motivation, what the scorer checks, and its runs. The area grouping and the chain column are ${src("ours")}</p>
      <div class="table-shell"><div class="table-scroll"><table class="simple cat"><thead><tr><th>Eval</th><th>Type</th><th>Scored by</th><th>Runs in</th><th>Chain</th><th>Pass rate<span class="subline">Internet + Skills</span></th></tr></thead>
      ${E.pillars.map(p => `<tbody><tr class="cat-p"><th colspan="6">${p.name}<span>${PILLAR_INFO[p.id].q}</span></th></tr>${PILLAR_INFO[p.id].areas.map(([a]) => { const list = evs.filter(ev => ev.pillar === p.id && AREA[ev.id] === a); return list.length ? `<tr class="cat-a"><th colspan="6">${a}</th></tr>${list.map(row).join("")}` : ""; }).join("")}</tbody>`).join("")}
      </table></div><div class="table-note"><span>Scored by: automatic checks, or a rubric that a grader model answers. Any eval can add a rubric to its automatic checks.</span><span>Pass rate: share of Internet + Skills runs that passed</span></div></div>
    </section>`;
  }

  // ---------- drawer: one panel, three levels (after view 4) ----------
  // Level 1: an agent on a set of evals (a leaderboard cell).  Level 2: an agent on one eval, with its runs.
  // Level 3: one run. The state lives in the URL (?d=agent~mode~scope~eval~run), so the browser's Back closes it
  // and a link can open it. Closing returns to the same scroll position and focus.
  const dialog = () => document.getElementById("detail");
  let dr = null, drPushed = false, drOpener = null;
  const scopeName = sc => sc === "shared" ? "Knowledge" : !sc || sc === "all" ? "All pillars" : sc.includes("-") ? `${E.pillars.find(p => p.id === sc.split("-")[0]).name} · ${sc.split("-").slice(1).join("-")}` : E.pillars.find(p => p.id === sc).name;
  const scopeFilter = sc => ev => sc === "shared" ? common(ev) : !sc || sc === "all" ? true : sc.includes("-") ? ev.pillar === sc.split("-")[0] && ev.type === sc.split("-").slice(1).join("-") : ev.pillar === sc;
  const encD = d => [d.agent, d.mode, d.scope || "", d.ev || "", d.run || ""].join("~");
  const decD = s => { const [agent, mode, scope, ev, run] = (s || "").split("~"); return agentById(agent) && ["vanilla", "internet", "skills"].includes(mode) ? { agent, mode, scope: scope || "", ev: evalById(ev) ? ev : "", run: +run || 0 } : null; };
  function setD(val, push) {
    const [p, q = ""] = location.hash.split("?"); const qs = new URLSearchParams(q);
    if (val) qs.set("d", val); else qs.delete("d");
    const h = p + (qs.toString() ? "?" + qs.toString() : "");
    if (push) history.pushState(null, "", h); else history.replaceState(null, "", h);
  }
  const runsFor = d => runsOf(evalById(d.ev), d.agent, d.mode);
  const runState = r => r.invalid ? "invalid" : r.pass ? "pass" : r.end === "time limit" ? "time limit" : "fail";
  const dotsOnly = rs => `<span class="dots">${rs.map(r => `<span class="dot ${r.invalid ? "x" : r.end === "time limit" ? "t" : r.pass ? "p" : "f"}"></span>`).join("")}</span>`;
  const heatCell = (k, n) => n ? `<span class="dscore" style="--p:${(k / n).toFixed(3)}"><b>${pct(k / n)}</b><small>${k}/${n}</small></span>` : `<span class="dscore na">no run</span>`;

  // Opening the panel locks the page's scroll (CSS) and hides its scrollbar: measure the bar first, so the
  // page can be padded by its width and doesn't shift sideways.
  // Focus goes to the panel itself (named by its title), not to its first button: on touch screens a
  // pre-focused Close looked already pressed.
  function showPanel() {
    document.documentElement.style.setProperty("--sbw", `${innerWidth - document.documentElement.clientWidth}px`);
    dialog().showModal();
    dialog().setAttribute("tabindex", "-1");
    dialog().focus({ preventScroll: true });
  }
  function openD(state, opener) {
    if (!dialog().open) { drOpener = opener || document.activeElement; }
    dr = { scope: "", ev: "", run: 0, ...state };
    if (!dialog().open) { setD(encD(dr), true); drPushed = true; paintD(); showPanel(); }
    else { setD(encD(dr), false); paintD(); }
  }
  function goD(patch) { dr = { ...dr, ...patch }; setD(encD(dr), false); paintD(); document.querySelector("#detail").scrollTop = 0; }
  // The panel closes at once; the history catches up after (Back is asynchronous).
  function closeD() {
    if (!dialog().open) return;
    dialog().close();
    if (drPushed) { drPushed = false; history.back(); }
    else setD(null, false);
  }
  // Called when the URL changes: open, move or close the panel to match it.
  function syncD() {
    const [, q = ""] = location.hash.split("?");
    const d = decD(new URLSearchParams(q).get("d"));
    if (!d) { if (dialog().open) dialog().close(); dr = null; drPushed = false; return; }
    dr = d; paintD(); if (!dialog().open) showPanel();
  }

  function paintD() {
    const a = agentById(dr.agent), ev = dr.ev ? evalById(dr.ev) : null;
    const back = dr.run ? `<button class="dback" data-dgo="eval">← All runs</button>` : ev && dr.scope ? `<button class="dback" data-dgo="list">← ${scopeName(dr.scope)} evals</button>` : "";
    const body = dr.run ? paintRun(a, ev) : ev ? paintEval(a, ev) : paintList(a);
    document.getElementById("detail-content").innerHTML = `<header class="drawer-header"><div class="drawer-heading">${body.head}</div><button id="close-detail" class="close-button" aria-label="Close details">Close ×</button></header><div class="drawer-content">${back}${body.main}</div>`;
  }

  // The panel's mode switch, laid out like the tables': the two agent modes together, Model only apart.
  // A mode with nothing to show stays visible but disabled.
  function dmodeSel(has) {
    const b = m => `<button data-dmode="${m}" aria-pressed="${m === dr.mode}"${has(m) ? "" : ` disabled title="${m === "vanilla" ? "No Model only evals here" : "Not run in this mode"}"`}>${m === "vanilla" ? "Model only" : modeName(m)}</button>`;
    return `<div class="tvsel dmodes" role="group" aria-label="Mode"><div class="segmented">${b("internet")}${b("skills")}</div><span class="tvsep" aria-hidden="true"></span><div class="segmented tv-alt">${b("vanilla")}</div></div>`;
  }

  // Level 1 · an agent on a set of evals
  function paintList(a) {
    const f = scopeFilter(dr.scope);
    const evs = E.evals.filter(ev => f(ev) && ev.modes.includes(dr.mode));
    const s = stats(dr.agent, dr.mode, ev => f(ev));
    const tile = (k, v) => `<div class="tile"><div class="k">${k}</div><div class="val">${v}</div></div>`;
    return {
      head: `<h2 id="detail-title">${esc(a.name)}</h2><p class="dsub">${harnessFor(a, dr.mode)} · ${modeName(dr.mode)} · ${scopeName(dr.scope)}</p><p class="dsum"><b>${pct(s.p)}</b> average pass rate over ${s.ran < s.evals ? `${s.ran} of ${s.evals} evals` : plural(s.ran, "eval")} · ${s.k} of ${s.n} runs passed</p>`,
      main: `${dmodeSel(m => E.evals.some(ev => f(ev) && ev.modes.includes(m)))}
        ${s.n ? `<div class="tiles">${tile("$ / pass", usd(s.costPerPass))}${tile("Cost / run", usd(s.costPerRun))}${tile("Tokens / run", tok(s.tokMed))}${tile("Time / run", s.timeMed + "s")}${dr.mode === "skills" ? tile("Skill read", pct(s.read)) : ""}</div><p class="fine">Cost per run is an average; tokens and time are medians.</p>` : ""}
        <div class="dlist">${evs.map(ev => { const rs = runsOf(ev, dr.agent, dr.mode), ok = rs.filter(r => !r.invalid), k = ok.filter(r => r.pass).length;
        return `<button class="drow2" data-dl="${ev.id}"><span class="dt"><b>${esc(ev.title)}</b><span class="dmeta">${ev.type} · ${GRADER_FILE[ev.grader] || ev.grader}${ev.released <= a.cutoff ? ' · <em>released before model cutoff</em>' : ""}</span></span>${rs.length ? dotsOnly(rs) : ""}${heatCell(k, ok.length)}<span class="dgo">›</span></button>`; }).join("") || '<p class="muted">No evals here in this mode.</p>'}</div>`,
    };
  }

  // Level 2 · an agent on one eval, with all its runs
  function paintEval(a, ev) {
    const rs = runsFor(dr), ok = rs.filter(r => !r.invalid), k = ok.filter(r => r.pass).length;
    const sample = rs[0] || E.agents.map(x => runsOf(ev, x.id, ev.modes[0])[0]).find(Boolean) || { checks: [] };
    return {
      head: `<h2 id="detail-title">${esc(ev.title)}</h2><p class="dsub">${esc(a.name)} · ${harnessFor(a, dr.mode)} · ${ev.type} · ${GRADER_FILE[ev.grader] || ev.grader}</p><p class="dsum">${ok.length ? `<b>${pct(k / ok.length)}</b> ${k} of ${ok.length} runs passed` : "No runs in this mode yet"}</p>`,
      main: `${dmodeSel(m => ev.modes.includes(m))}
        <section class="dsec"><h3>Prompt</h3><pre>${esc(ev.prompt)}</pre></section>
        <section class="dsec"><h3>What the scorer checks <span class="muted mono">${GRADER_FILE[ev.grader] || ev.grader}</span></h3><ol class="checks">${sample.checks.map(c => `<li>${esc(c.name)}${c.expected ? ` <span class="muted mono">· expects ${esc(c.expected)}</span>` : ""}</li>`).join("")}</ol><p class="fine">A run passes only if every check passes.</p></section>
        <section class="dsec"><h3>Runs</h3>${rs.length ? `<div class="table-shell"><table class="simple druns"><thead><tr><th>Run</th><th>Result</th><th>Checks</th><th>Time</th><th>Tokens</th><th>Cost</th><th></th></tr></thead><tbody>${rs.map(r => `<tr data-drun="${r.k}" tabindex="0"><td>Run ${r.k}</td><td><span class="status ${r.invalid ? "invalid" : r.pass ? "pass" : "fail"}">${runState(r).toUpperCase()}</span></td><td class="mono">${r.checks.filter(c => c.ok).length}/${r.checks.length}</td><td class="mono">${r.durationSec}s</td><td class="mono">${tok(r.tokens.input + r.tokens.output)}</td><td class="mono">${usd(r.cost)}</td><td class="dgo">›</td></tr>`).join("")}</tbody></table></div>` : '<p class="muted">This mode is supported, but no runs are recorded yet.</p>'}</section>
        <p class="dfull"><a href="#/eval/${ev.id}">Open the eval page, every agent and mode ↗</a></p>`,
    };
  }

  // Level 3 · one run
  function paintRun(a, ev) {
    const rs = runsFor(dr), r = rs[dr.run - 1];
    if (!r) { dr.run = 0; return paintEval(a, ev); }
    const st8 = runState(r);
    const strip = `<div class="rstrip" role="group" aria-label="Runs">${rs.map(x => `<button data-drun="${x.k}" aria-pressed="${x.k === r.k}" class="${x.invalid ? "x" : x.pass ? "p" : "f"}">Run ${x.k} ${x.invalid ? "·" : x.pass ? "✓" : "✗"}</button>`).join("")}</div>`;
    const warn = [r.invalid ? '<div class="banner"><b>Invalid run.</b> The agent fetched our own eval file from the web. It is kept for transparency and left out of every score.</div>' : "",
      dr.mode === "skills" && !r.skillRead ? '<div class="banner">The skill was available, but the agent <b>didn\'t open it</b> in this run.</div>' : "",
      ev.released <= a.cutoff ? '<div class="banner">This eval was published before the model\'s training cutoff, so the answer may be in its training data.</div>' : ""].join("");
    return {
      head: `<h2 id="detail-title"><span class="status ${r.invalid ? "invalid" : r.pass ? "pass" : "fail"}">${st8.toUpperCase()}</span> Run ${r.k} of ${rs.length}</h2><p class="dsub">${esc(ev.title)} · ${esc(a.name)} · ${modeName(dr.mode)}</p>`,
      main: `${strip}${warn}
        <div class="tiles"><div class="tile"><div class="k">Checks</div><div class="val">${r.checks.filter(c => c.ok).length} / ${r.checks.length}</div></div><div class="tile"><div class="k">Tokens</div><div class="val">${tok(r.tokens.input + r.tokens.output)}</div></div><div class="tile"><div class="k">Cost</div><div class="val">${usd(r.cost)}</div></div><div class="tile"><div class="k">Time</div><div class="val">${r.durationSec}s</div></div>${dr.mode === "skills" ? `<div class="tile"><div class="k">Skill</div><div class="val">${r.skillRead ? "read" : "not read"}</div></div>` : ""}</div>
        <section class="verdict"><div class="vh"><h3>Scorer verdict</h3><span class="muted mono">${GRADER_FILE[ev.grader] || ev.grader}</span></div>${r.checks.map((c, j) => `<div class="ck"><span class="${c.ok ? "positive" : "negative"}">${c.ok ? "✓" : "✗"}</span><span>${j + 1}. ${esc(c.name)}</span><button class="dstep" data-dstep="${c.step}">step ${c.step}</button><div class="ex"><span>expected <b>${esc(c.expected)}</b></span><span>got <b class="${c.ok ? "" : "negative"}">${esc(c.got)}</b></span>${c.reason ? `<span>${esc(c.reason)}</span>` : ""}</div></div>`).join("")}</section>
        <details class="dsec" ${r.steps.length <= 8 ? "open" : ""}><summary><h3>Transcript <span class="muted mono">${r.steps.length} steps</span></h3></summary>${r.steps.map((s, i) => `<div class="step ${s.flagged ? "flag" : ""}" id="dstep-${i + 1}"><span class="no">#${i + 1}</span><div><span class="kind ${s.kind}">${s.kind}</span><pre>${esc(s.text)}</pre></div></div>`).join("")}</details>
        ${r.chain ? `<section class="dsec"><h3>Chain state after the run</h3><div class="table-shell"><table class="simple"><thead><tr><th>Read</th><th>Before</th><th>After</th><th>Check</th></tr></thead><tbody>${r.chain.map(c => `<tr><td class="mono">${esc(c[0])}</td><td class="mono">${esc(c[1])}</td><td class="mono">${esc(c[2])}</td><td class="${c[3] ? "positive" : "negative"}">${c[3] ? "✓" : "✗"}</td></tr>`).join("")}</tbody></table></div></section>` : ""}
        ${r.diff ? `<section class="dsec"><h3>${ev.grader === "tests" ? "Files" : "Answer"}</h3><div class="file-list">${r.files.map(esc).join("<br>")}</div><pre>${r.diff.split("\n").map(l => `<span class="${l.startsWith("+") ? "positive" : l.startsWith("-") ? "negative" : ""}">${esc(l)}</span>`).join("\n")}</pre></section>` : ""}
        <p class="dfull"><a href="#/run/${encodeURIComponent(r.id)}">Open the run page ↗</a></p>`,
    };
  }

  // ---------- Compare page (after Vals AI) ----------
  function renderCompare(list) {
    const ids = (list || "").split(",").filter(id => agentById(id)).slice(0, 5);
    if (!ids.length) { const top = E.agents.map(a => ({ a, s: stats(a.id, "skills") })).sort((x, y) => y.s.p - x.s.p).slice(0, 3).map(x => x.a.id); ids.push(...top); }
    // Compare follows the mode chosen on Results. Model only drops the agent rows: cost, tokens, skills.
    const mode = st.tv, vanilla = mode === "vanilla";
    const rowsDef = [
      ["Overall", a => stats(a, mode), "rate"],
      ...E.pillars.map(p => [p.name, a => stats(a, mode, ev => ev.pillar === p.id), "rate", `var(--p-${p.id})`]),
      ...(vanilla ? [] : [
        ["Lift from skills (same evals)", a => ({ p: stats(a, "skills").p - stats(a, "internet").p }), "pp"],
        ...(mode === "skills" ? [["Skill read", a => ({ p: stats(a, "skills").read }), "readp"]] : []),
        ["Cost per passed run ↓", a => ({ p: stats(a, mode).costPerPass }), "usd"],
        ["Tokens per run ↓", a => ({ p: stats(a, mode).tokMed }), "tok"]])
    ];
    const cmpPalette = ["#3ecf8e", "#60a5fa", "#f59e0b", "#a78bfa", "#f472b6"];
    const bestOf = (vals, kind) => { const xs = vals.map(v => v.p).filter(isFinite); if (!xs.length) return NaN; return kind === "usd" || kind === "tok" ? Math.min(...xs) : Math.max(...xs); };
    const fmt = (v, kind) => kind === "rate" ? (v.n ? pct(v.p) : `<span class="muted" title="${vanilla ? "No Model only evals in this pillar" : "No runs"}">–</span>`) : kind === "pp" ? (isNaN(v.p) ? "–" : pp(v.p)) : kind === "readp" ? pct(v.p) : kind === "usd" ? usd(v.p) : tok(v.p);
    const table = rowsDef.map(([name, fn, kind, pc]) => { const vals = ids.map(fn); const b = bestOf(vals, kind); return `<tr><th>${pc ? `<span class="sw" style="background:${pc}"></span>` : ""}${name}</th>${vals.map(v => `<td class="${v.p === b ? "best" : ""}">${fmt(v, kind)}</td>`).join("")}</tr>`; }).join("");
    root.querySelector("#main").innerHTML = `<div class="page" style="max-width:none">
      <div class="crumbs"><a href="${boardHash()}">Results</a> / Compare</div>
      <div class="pagehead"><h1>Compare configurations</h1><a class="backbtn" href="${boardHash()}">← Back to results</a></div>
      <div class="pickrow"><span class="muted">Select up to 5:</span>${E.agents.map(a => `<button class="pick" data-pick="${a.id}" aria-pressed="${ids.includes(a.id)}">${ids.includes(a.id) ? "✓ " : ""}${esc(a.name)}</button>`).join("")}</div>
      <div class="toolbar tvbar"><div class="tvsel" role="group" aria-label="Mode"><div class="segmented">${[["internet", "Internet"], ["skills", "Internet + Skills"]].map(([id, t]) => `<button data-cmpmode="${id}" aria-pressed="${mode === id}">${t}</button>`).join("")}</div><span class="tvsep" aria-hidden="true"></span><div class="segmented tv-alt"><button data-cmpmode="vanilla" aria-pressed="${vanilla}">Model only</button></div></div>${vanilla ? modelOnlyNote() : ""}</div>
      <div class="table-shell"><div class="table-scroll"><table class="simple cmp"><thead><tr><th></th>${ids.map(id => `<th><span class="sw" style="background:${cmpPalette[ids.indexOf(id)]}"></span>${esc(agentById(id).name)}<span class="subline" style="display:block">${vanilla ? orgOf[id] : harnessFor(agentById(id), mode)}</span></th>`).join("")}</tr></thead><tbody>${table}</tbody></table></div><div class="table-note"><span>Best value in each row is highlighted${vanilla ? "" : " · ↓ lower is better"}</span></div></div>
    </div>`;
    root.querySelectorAll("[data-pick]").forEach(b => b.onclick = () => { const id = b.dataset.pick; const next = ids.includes(id) ? ids.filter(x => x !== id) : ids.length < 5 ? [...ids, id] : ids; location.hash = "#/compare/" + next.join(","); });
    root.querySelectorAll("[data-cmpmode]").forEach(b => b.onclick = () => { st.tv = b.dataset.cmpmode; renderCompare(ids.join(",")); root.querySelector(`[data-cmpmode="${st.tv}"]`)?.focus({ preventScroll: true }); });
  }


  // ---------- eval page ----------
  function renderEval(id) {
    const ev = evalById(id); if (!ev) { root.querySelector("#main").innerHTML = '<p class="muted">No eval with that id.</p>'; return; }
    const p = E.pillars.find(x => x.id === ev.pillar);
    const sample = E.agents.map(a => runsOf(ev, a.id, ev.modes[ev.modes.length - 1])[0]).find(Boolean) || { checks: [] };
    const pool = m => { const rs = E.agents.flatMap(a => runsOf(ev, a.id, m)).filter(r => !r.invalid); const k = rs.filter(r => r.pass).length; return { k, n: rs.length, p: rs.length ? k / rs.length : NaN }; };
    const LBL = { vanilla: ["Model only", "Pass rate", "var(--v)"], internet: ["Internet", "Pass rate", "var(--i)"], skills: ["Internet + Skills", "Pass rate", "var(--s)"] };
    const order = ["vanilla", "internet", "skills"].filter(m => ev.modes.includes(m));
    const cols = ["internet", "skills", "vanilla"];
    const cell = (a, m) => {
      if (!ev.modes.includes(m)) return `<td class="muted na-cell">${m === "vanilla" ? "needs tools" : "not run"}</td>`;
      const rs = runsOf(ev, a.id, m), ok = rs.filter(r => !r.invalid), k = ok.filter(r => r.pass).length;
      if (!rs.length) return '<td><span class="pending">no run yet</span></td>';
      return `<td><button class="pr" data-dev="${a.id}~${m}~${ev.id}" style="--p:${(k / ok.length).toFixed(3)}" title="${esc(a.name)} · ${modeName(m)}: open the runs"><span class="v">${pct(k / ok.length)}</span><span class="n">${k}/${ok.length} runs</span></button></td>`;
    };
    const runs = E.agents.flatMap(a => ev.modes.flatMap(m => runsOf(ev, a.id, m).map(r => ({ r, a, m }))));
    root.querySelector("#main").innerHTML = `<div class="page">
      <div class="crumbs"><a href="${evalsHash()}">Results</a> / ${p.name} / ${esc(ev.title)}</div>
      <div><h1>${esc(ev.title)}</h1><div class="eval-id" style="font-size:11px;margin-top:6px">released ${ev.released}</div></div>
      <div class="chipline"><span class="chip">${p.name}</span><span class="chip">${ev.type}</span><span class="chip">scored by: ${GRADER_FILE[ev.grader] || ev.grader}</span><span class="chip">modes: ${ev.modes.map(m => m === "vanilla" ? "model only" : modeName(m).toLowerCase()).join(" · ")}</span></div>
      <div class="evsteps">${order.map(m => { const s = pool(m); return `<div class="evstep"><span class="pk">${LBL[m][0]}</span><b>${pct(s.p)}</b><span class="ltrack"><i style="width:${(s.p || 0) * 100}%;background:${LBL[m][2]}"></i></span><span class="fine">${LBL[m][1]} · ${s.k} of ${s.n} runs, all agents</span></div>`; }).join("")}</div>
      <div class="ev2"><div><h3>Motivation</h3><p class="why" style="margin-top:6px">${esc(ev.why)}</p></div>
        <div><h3>What the scorer checks <span class="muted mono" style="font-weight:400">${GRADER_FILE[ev.grader] || ev.grader}</span></h3><ol class="checks" style="margin-top:8px">${sample.checks.map(c => `<li>${esc(c.name)}${c.expected ? ` <span class="muted mono" style="font-size:11px">· expects ${esc(c.expected)}</span>` : ""}</li>`).join("")}</ol><p class="fine" style="margin-top:6px">A run passes only if every check passes.</p></div></div>
      <div><h3 style="margin-bottom:8px">Prompt</h3><pre>${esc(ev.prompt)}</pre></div>
      <div><h3 style="margin-bottom:8px">Results by agent</h3><div class="table-shell"><div class="table-scroll"><table class="simple evres"><thead><tr><th>Agent</th>${cols.map(m => `<th>${modeName(m)}</th>`).join("")}</tr></thead><tbody>${E.agents.map(a => `<tr><td><b>${esc(a.name)}</b> <span class="muted" style="font-size:11px">${a.harness}</span></td>${cols.map(m => cell(a, m)).join("")}</tr>`).join("")}</tbody></table></div><div class="table-note"><span>Share of runs that passed. Click a cell for its runs.</span></div></div></div>
      <details><summary style="cursor:pointer"><h3 style="display:inline">All runs (${runs.length})</h3> <span class="muted">· one row per run</span></summary><div class="table-shell" style="margin-top:8px"><div class="table-scroll"><table class="simple"><thead><tr><th>Run</th><th>Agent</th><th>Mode</th><th>Result</th><th>Checks</th><th>Tokens</th><th>Time</th><th>Cost</th></tr></thead><tbody>${runs.map(({ r, a, m }) => `<tr><td><a href="#/run/${encodeURIComponent(r.id)}">run ${r.k}</a></td><td>${esc(a.name)}</td><td class="muted">${modeName(m)}${m === "skills" ? (r.skillRead ? " · skill read" : ' · <span style="color:var(--amber)">skill not read</span>') : ""}</td><td>${r.invalid ? '<span class="status invalid">INVALID</span>' : r.pass ? '<span class="positive">pass</span>' : `<span class="negative">${r.end === "done" ? "fail" : r.end}</span>`}</td><td class="mono">${r.checks.filter(c => c.ok).length}/${r.checks.length}</td><td class="mono">${tok(r.tokens.input + r.tokens.output)}</td><td class="mono">${r.durationSec}s</td><td class="mono">${usd(r.cost)}</td></tr>`).join("")}</tbody></table></div></div></details>
    </div>`;
  }

  // ---------- run page ----------
  function renderRun(id) {
    let run, ev, agent, mode;
    E.evals.forEach(e => E.agents.forEach(a => E.modes.forEach(m => runsOf(e, a.id, m.id).forEach(r => { if (r.id === id) { run = r; ev = e; agent = a; mode = m.id; } }))));
    if (!run) { root.querySelector("#main").innerHTML = '<p class="muted">No run with that id.</p>'; return; }
    const sibs = runsOf(ev, agent.id, mode), prev = sibs[run.k - 2], next = sibs[run.k];
    const st8 = run.invalid ? "invalid" : run.pass ? "pass" : "fail";
    const firstFail = run.checks.find(c => !c.ok);
    const tabs = ["Transcript", run.chain ? "Chain state" : ev.grader === "tests" ? "Files" : "Answer", "Raw"];
    root.querySelector("#main").innerHTML = `<div class="page">
      <div class="crumbs"><a href="${evalsHash()}">Results</a> / <a href="#/eval/${ev.id}">${esc(ev.title)}</a> / ${esc(agent.name)} · ${modeName(mode)} / run ${run.k} of ${sibs.length}</div>
      <div class="runhead"><span class="status ${st8}">${st8.toUpperCase()}</span><h1>${esc(ev.title)}</h1><span class="rstrip page-strip">${sibs.map(x => `<a href="#/run/${encodeURIComponent(x.id)}" class="${x.invalid ? "x" : x.pass ? "p" : "f"}"${x.k === run.k ? ' aria-current="true"' : ""}>Run ${x.k} ${x.invalid ? "·" : x.pass ? "✓" : "✗"}</a>`).join("")}</span></div>
      <div class="chipline"><span class="chip">${esc(agent.name)}</span><span class="chip">${harnessFor(agent, mode)}</span><span class="chip">${modeName(mode)}</span><span class="chip">${ev.type} · ${GRADER_FILE[ev.grader] || ev.grader}</span><span class="chip">released ${ev.released}</span>${ev.released <= agent.cutoff ? '<span class="chip warn">eval released before model cutoff</span>' : ""}</div>
      ${run.invalid ? '<div class="banner"><b>Invalid run.</b> In Internet mode the agent fetched our own eval file (step 2). Kept for transparency, excluded from every score.</div>' : ""}
      ${mode === "skills" && !run.skillRead ? '<div class="banner">The skill was available, but the agent <b>didn\'t open it</b> in this run.</div>' : ""}
      <div class="tiles">
        <div class="tile"><div class="k">Checks</div><div class="val">${run.checks.filter(c => c.ok).length} / ${run.checks.length}</div></div>
        <div class="tile"><div class="k">Tokens</div><div class="val">${tok(run.tokens.input + run.tokens.output)}</div><div class="muted mono" style="font-size:10.5px">in ${tok(run.tokens.input - run.cached)} · cache ${tok(run.cached)} · out ${tok(run.tokens.output)}</div></div>
        <div class="tile"><div class="k">Cost</div><div class="val">${usd(run.cost)}</div></div>
        <div class="tile"><div class="k">Time</div><div class="val">${run.durationSec}s</div><div class="muted mono" style="font-size:10.5px">ended: ${run.end}</div></div>
        <div class="tile"><div class="k">${mode === "skills" ? "Skill" : "Network"}</div><div class="val">${mode === "skills" ? (run.skillRead ? "read" : "not read") : mode === "vanilla" ? "off" : "on"}</div></div>
      </div>
      <section class="verdict"><div class="vh"><h3>Scorer verdict</h3><span class="muted mono" style="font-size:11px">${GRADER_FILE[ev.grader] || ev.grader}${ev.grader === "judge" ? " · a judge model, never the one under test" : ""}</span>${firstFail ? `<a href="#" data-step="${firstFail.step}" style="margin-left:auto;font:11px var(--mono);color:var(--accent)">Jump to first failure →</a>` : ""}</div>
        ${run.checks.map((c, j) => `<div class="ck"><span class="${c.ok ? "positive" : "negative"}">${c.ok ? "✓" : "✗"}</span><span>${j + 1}. ${esc(c.name)}</span><a href="#" data-step="${c.step}">step ${c.step}</a><div class="ex"><span>expected <b>${esc(c.expected)}</b></span><span>got <b class="${c.ok ? "" : "negative"}">${esc(c.got)}</b></span>${c.reason ? `<span>${esc(c.reason)}</span>` : ""}</div></div>`).join("")}
        ${run.grader.note ? `<div class="ck"><span></span><span class="muted">${esc(run.grader.note)}</span></div>` : ""}
      </section>
      <div class="page-tabs" role="tablist">${tabs.map((t, i) => `<button data-tab5="${t}" aria-pressed="${i === 0}">${t}</button>`).join("")}</div>
      <div id="tabbody"></div>
      <div><h3 style="margin-bottom:4px">Example command</h3><p class="fine" style="margin-bottom:8px">Illustrative, based on the system proposal in PR #5.</p><pre>inspect eval runner/tasks.py@ethevals -T mode=${mode}${mode === "vanilla" ? "" : ` -T agent=${agent.harness.toLowerCase().replace(/ /g, "_")}`} \\
  --sample-id ${ev.pillar}/${ev.id} --model ${agent.id} --epochs ${sibs.length}</pre></div>
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


  // =====================================================================
  // Site: pages, shell and router
  // =====================================================================
  const REPO = "https://github.com/BuidlGuidl/ethevals";
  const totalRuns = E.evals.reduce((n, ev) => n + E.agents.reduce((m, a) => m + E.modes.reduce((k, md) => k + runsOf(ev, a.id, md.id).length, 0), 0), 0);
  const nKnow = E.evals.filter(ev => ev.modes.includes("vanilla")).length;
  const reportHash = () => `#/?show=${st.tv}&sort=${st.sort}`;
  const evalsHash = () => `#/#evals?show=${st.tv}&sort=${st.sort}`;
  const jump = (id, label) => `<button class="jump" data-jump="${id}">${label}</button>`;
  const fake = ""; // the "Synthetic data" label is off: everyone viewing the prototype knows the data is mock
  const topBy = (mode, f) => E.agents.map(a => ({ a, s: stats(a.id, mode, f) })).sort((x, y) => (y.s.p || 0) - (x.s.p || 0));

  // ---------- key findings, worded from the data ----------
  // Each sentence checks what it claims: a gap counts only when it is larger than its rerun margin.
  const listOf = xs => xs.length < 2 ? xs.join("") : xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1];
  function findings(rows) {
    const nm = r => `<b>${esc(r.a.name)}</b>`;
    const ranked = rows.filter(r => r.s.n).sort((x, y) => y.s.p - x.s.p), lead = ranked[0];
    const tied = ranked.filter(r => pct(r.s.p) === pct(lead.s.p));
    const close = ranked.slice(tied.length).filter(r => lead.s.p - r.s.p < 1.96 * Math.sqrt(lead.s.se ** 2 + r.s.se ** 2));
    const leadText = `${tied.length > 1 ? `${listOf(tied.map(nm))} lead with skills, level at ${pct(lead.s.p)}.` : `${nm(lead)} on ${esc(lead.a.harness)} has the highest pass rate with skills.`} ${close.length ? `${listOf(close.map(r => `${nm(r)} (${pct(r.s.p)})`))} ${close.length === 1 ? "is" : "are"} close enough that a rerun could change the order.` : ranked[tied.length] ? `The next, ${nm(ranked[tied.length])} (${pct(ranked[tied.length].s.p)}), is clearly behind.` : ""}`;

    const ls = rows.filter(r => !isNaN(r.lift)).sort((x, y) => y.lift - x.lift);
    const clear = liftClear;
    const up = ls.filter(r => r.lift > 0 && clear(r)), down = ls.filter(r => r.lift < 0 && clear(r)), flat = ls.filter(r => !clear(r));
    const liftText = [
      up.length === ls.length ? "Skills raise the pass rate of every agent on the same evals." : `Skills raise the pass rate of ${up.length} of ${ls.length} agents on the same evals.`,
      up.length ? `${nm(up[0])} gains the most.` : "",
      flat.length ? `${listOf(flat.map(r => `${nm(r)}'s ${pp(r.lift)}`))} ${flat.length === 1 ? "is" : "are"} within run-to-run noise.` : "",
      down.length ? `${listOf(down.map(nm))} score${down.length === 1 ? "s" : ""} lower with skills.` : ""
    ].filter(Boolean).join(" ");

    const priced = rows.filter(r => isFinite(r.s.costPerPass)).sort((x, y) => x.s.costPerPass - y.s.costPerPass), cheap = priced[0];
    const ref = priced.find(r => tied.includes(r));
    const costText = !cheap ? "" : `${nm(cheap)} has the cheapest passed run with skills, at a ${pct(cheap.s.p)} pass rate. ${tied.includes(cheap) ? `It is also ${tied.length > 1 ? "one of the leaders" : "the top scorer"}.` : ref ? `${tied.length > 1 ? "The cheaper of the leaders" : "The top scorer"}, ${nm(ref)}, costs ${usd(ref.s.costPerPass)} per passed run, ${Math.round(ref.s.costPerPass / cheap.s.costPerPass)}× more.` : ""}`;

    const pl = E.pillars.map((p, j) => { const xs = rows.map(r => r.pillars[j].p).filter(isFinite); return { p, r: xs.reduce((s, x) => s + x, 0) / xs.length }; }).filter(x => isFinite(x.r)).sort((x, y) => x.r - y.r);
    const pillarText = `<b>${pl[0].p.name}</b> is the hardest pillar: the agents average ${pct(pl[0].r)} with skills. <b>${pl[pl.length - 1].p.name}</b> is the easiest (${pct(pl[pl.length - 1].r)}).`;

    const cards = [[pct(lead.s.p), leadText], [ls.length ? `${pp(ls[ls.length - 1].lift)} to ${pp(ls[0].lift)}` : "–", liftText], [cheap ? usd(cheap.s.costPerPass) : "–", costText], [pct(pl[0].r), pillarText]];
    return `<div class="finds">${cards.map(([big, text]) => `<div class="find"><span class="fbig">${big}</span><p>${text}</p></div>`).join("")}</div>`;
  }

  // ---------- Home ----------
  function renderHome() {
    st.pillar = "all";
    const top = topBy("skills", () => true).slice(0, 3);
    const steps = [["Write an eval", "A folder with a prompt, the files the agent starts with, and a grader. Anyone adds one by pull request."], ["Run it in isolation", "Every run gets fresh containers: the agent, a local chain when the eval needs one, and a grader the agent can't reach."], ["Grade and publish", "Named checks decide pass or fail. Each eval runs several times, and every result links to its transcript."]];
    return `<header class="hero6 home"><div class="hero-l"><p class="eyebrow">The open benchmark for AI on Ethereum</p><h1>How well do AI agents handle Ethereum?</h1>
        <p class="lead">We test AI agents, and the models behind them, on real Ethereum work: understanding the protocol, sending transactions, building contracts and securing them. Every task, grader, run and transcript is public, and anyone can run the same evals.</p>
        <div class="ctas"><a class="btn primary" href="${reportHash()}">See the results →</a><a class="btn" href="#/how">How we evaluate</a></div></div></header>
      <section class="hsec"><div class="hsec-h"><h2>Top agents with skills</h2><a class="more" href="${reportHash()}">All results →</a></div>
        <div class="minilb">${top.map(({ a, s }) => `<a class="mrow" href="${reportHash()}"><span class="mname"><b>${esc(a.name)}</b><span>${esc(a.harness)} · ${a.effort}</span></span><span class="ltrack"><i style="width:${s.p * 100}%;background:var(--s)"></i><u style="left:${s.lo * 100}%;width:${(s.hi - s.lo) * 100}%"></u></span><span class="mval">${pct(s.p)} <small>${pm(s)}</small></span></a>`).join("")}</div>
        <p class="fine">Average pass rate with skills over all ${E.evals.length} evals. ${fake}</p></section>
      <section class="hsec"><div class="hsec-h"><h2>What we measure</h2><a class="more" href="#/method">Method →</a></div>
        <div class="p4">${E.pillars.map(p => `<a class="p4c" href="#/evals?pillar=${p.id}"><span class="pk">${p.name}<span>${E.evals.filter(ev => ev.pillar === p.id).length} evals</span></span><b>${PILLAR_INFO[p.id].q}</b><span class="p4a">${PILLAR_INFO[p.id].areas.map(x => x[0]).join(" · ")}</span></a>`).join("")}</div></section>
      <section class="hsec"><div class="hsec-h"><h2>How it works</h2><a class="more" href="#/how">How it works →</a></div>
        <ol class="steps3">${steps.map(([h, t]) => `<li><h3>${h}</h3><p>${t}</p></li>`).join("")}</ol></section>
      ${threeSteps()}
      ${runBlock()}`;
  }
  function threeSteps() {
    const ev = evalById("erc-8004-quiz");
    const pool = m => { const rs = E.agents.flatMap(a => runsOf(ev, a.id, m)).filter(r => !r.invalid); return wilson(rs.filter(r => r.pass).length, rs.length); };
    const steps = [["vanilla", "What the model remembers", "the bare model, no tools", "var(--v)"], ["internet", "What an agent finds by searching", "an agent with the web", "var(--i)"], ["skills", "What skills add", "the same agent plus ethskills", "var(--s)"]];
    return `<section class="hsec"><div class="hsec-h"><h2>One eval, three steps</h2><a class="more" href="#/eval/${ev.id}">Open this eval →</a></div>
      <div class="three"><div class="tq"><span class="pk">Concepts · quiz · all three modes</span><p class="tprompt">which ERC gives AI agents onchain identity, reputation and validation registries? reply with just the number, nothing else.</p><span class="tans">grader/answer.txt <b>8004</b></span><p class="fine">ERC-8004 is recent, so a model without the web or skills may not know it. The example comes from the eval spec. ${src("spec")}</p></div>
      <div class="tbars">${steps.map(([m, h, sub, c]) => { const s = pool(m); return `<div class="tstep"><span class="th"><b>${h}</b><span>${sub}</span></span><span class="ltrack"><i style="width:${s.p * 100}%;background:${c}"></i><u style="left:${s.lo * 100}%;width:${(s.hi - s.lo) * 100}%"></u></span><span class="mval">${pct(s.p)} <small>${pm(s)}</small></span></div>`; }).join("")}<p class="fine">Share of runs that answered correctly, across all ${E.agents.length} models or agents. A quiz that runs in all three modes shows how much each step adds. ${fake}</p></div></div></section>`;
  }
  const runBlock = () => `<section class="table-shell runit"><h3>Run it on your AI</h3><p class="muted">Run the same evals with your own model, harness or skills, and compare against our numbers.</p><pre># the knowledge quizzes, straight from Hugging Face
inspect eval hf/ethereum-foundation/hf-ethevals-dataset --model openrouter/qwen/qwen3.5-397b-a17b

# one eval with your agent and skills, 3 runs, from the repo
inspect eval runner/tasks.py@ethevals -T mode=skills -T agent=claude_code \\
  --sample-id building/erc20-points-token --model anthropic/claude-opus-5 --epochs 3</pre><p class="muted fine">Commands from the system proposal in <a href="${REPO}/pull/5" target="_blank" rel="noopener">PR #5</a>. They are illustrative: the runner and the dataset don't exist yet.</p></section>`;

  // ---------- Results: findings and two tables (agents, then what bare models know) ----------
  // The landing page is the results page: the question, what we measure, the key findings (written by hand
  // for each release, so placeholders until real results exist), the leaderboard and every eval.
  function renderReport() {
    const rows = agentRows();
    const nEv = E.evals.filter(ev => ev.modes.includes("skills")).length;
    // Key findings are hidden until the results are real; set to true to bring them back.
    const SHOW_FINDINGS = false;
    const finding = n => `<li><span class="kfn">${n}</span><div><b>Key finding ${n}</b><p>One or two sentences on a result worth highlighting, with the number behind it.</p></div></li>`;
    return `${landHero()}
      ${SHOW_FINDINGS ? `<section class="lsec" id="findings"><h2>Key findings</h2><ol class="kf">${[1, 2, 3].map(finding).join("")}</ol><p class="fine">Placeholders: written by hand for each release, once the results are real.</p></section>` : ""}
      <section class="rsec" id="agents"><div class="rsec-h"><h2>Leaderboard</h2><a class="backbtn" href="#/compare">Compare configurations →</a></div><div class="toolbar tvbar">${viewSel()}${viewIntro(nEv)}</div>${resultsTable(rows)}</section>
      <p class="readnote"><b>How to read it.</b> A run passes only if it meets every check of its eval. Each eval runs 3–5 times per agent and mode; its score is the share of runs that passed, and a table score is the average over its evals.</p>
      ${evalsSection()}`;
  }

  // ---------- Results header ----------
  // After ethevals.com: the logo, the release under it like a version line, then the tagline, one sentence on
  // what we do and the four pillars by name. The logo is the nav's brand drawn large, so it can fly up into the
  // nav on scroll: the name with its square in clean, the block letters in geek. Both are in the page; each
  // look's CSS shows its own.
  // The block letters are the ones on ethevals.com (github.com/austintgriffith/ethevals, index.html).
  const ASCII_LOGO = [
    "███████╗████████╗██╗  ██╗███████╗██╗   ██╗ █████╗ ██╗     ███████╗",
    "██╔════╝╚══██╔══╝██║  ██║██╔════╝██║   ██║██╔══██╗██║     ██╔════╝",
    "█████╗     ██║   ███████║█████╗  ██║   ██║███████║██║     ███████╗",
    "██╔══╝     ██║   ██╔══██║██╔══╝  ╚██╗ ██╔╝██╔══██║██║     ╚════██║",
    "███████╗   ██║   ██║  ██║███████╗ ╚████╔╝ ██║  ██║███████╗███████║",
    "╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚══════╝",
  ];
  // Drawn as shapes from the same text, one monospace cell per character: a block for █ and double lines
  // for ═ ║ ╗ ╔ ╝ ╚. It looks the same whatever fonts are installed, and scales with the viewBox on phones.
  function asciiLogo(id = "glogo-g") {
    const cw = 10, ch = 19, cx = cw / 2, cy = ch / 2, d = 2.1;
    // each double-line glyph as two polylines, in cell coordinates
    const LINES = {
      "═": [[[0, cy - d], [cw, cy - d]], [[0, cy + d], [cw, cy + d]]],
      "║": [[[cx - d, 0], [cx - d, ch]], [[cx + d, 0], [cx + d, ch]]],
      "╗": [[[0, cy - d], [cx + d, cy - d], [cx + d, ch]], [[0, cy + d], [cx - d, cy + d], [cx - d, ch]]],
      "╔": [[[cw, cy - d], [cx - d, cy - d], [cx - d, ch]], [[cw, cy + d], [cx + d, cy + d], [cx + d, ch]]],
      "╝": [[[0, cy + d], [cx + d, cy + d], [cx + d, 0]], [[0, cy - d], [cx - d, cy - d], [cx - d, 0]]],
      "╚": [[[cw, cy + d], [cx - d, cy + d], [cx - d, 0]], [[cw, cy - d], [cx + d, cy - d], [cx + d, 0]]],
    };
    const blocks = [], lines = [];
    ASCII_LOGO.forEach((row, y) => {
      // runs of █ become one rectangle, so no seams show between cells
      row.replace(/█+/g, (run, x) => { blocks.push(`<rect x="${x * cw}" y="${y * ch}" width="${run.length * cw}" height="${ch}"/>`); return run; });
      [...row].forEach((c, x) => (LINES[c] || []).forEach(pl => lines.push("M" + pl.map(([px, py]) => `${x * cw + px} ${y * ch + py}`).join("L"))));
    });
    const w = ASCII_LOGO[0].length * cw, h = ASCII_LOGO.length * ch;
    return `<svg viewBox="0 0 ${w} ${h}" aria-hidden="true"><defs><linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="${w}" y2="0"><stop offset="0" stop-color="#8c8dfc"/><stop offset=".55" stop-color="#627eea"/><stop offset="1" stop-color="#62d3e5"/></linearGradient></defs><g fill="url(#${id})">${blocks.join("")}</g><path d="${lines.join("")}" fill="none" stroke="url(#${id})" stroke-width="1.1"/></svg>`;
  }
  function landHero() {
    const pillars = E.pillars.map(p => `<b>${p.name}</b>`);
    return `<header class="lhero">
        <div class="lh-brand"><h1 class="lh-logo" aria-label="ETH Evals"><span class="lh-word" aria-hidden="true">ETH Evals</span><span class="lh-ascii" aria-hidden="true">${asciiLogo()}</span></h1>
        <p class="lh-plate"><span><span class="lh-ver">${S.version}</span><span title="Suite hash">${S.hash}</span><span title="Data date">${S.date}</span></span><span><span><b>${E.evals.length}</b> evals</span><span><b>${E.agents.length}</b> agents</span><span><b>${totalRuns.toLocaleString("en")}</b> runs</span></span></p></div>
        <p class="lh-tag">The Open Benchmark for AI on Ethereum</p>
        <p class="lh-desc">We test AI agents, and the models behind them, on real Ethereum work. Every task, run and transcript is public, and anyone can run the same evals.</p>
        <p class="lh-pillars">We evaluate <a href="#/how#hw-pillars" title="What each pillar covers">four pillars</a>: ${listOf(pillars)}.</p>
      </header>`;
  }

  // ---------- Results by eval ----------
  // The eval-by-eval matrix, under the leaderboard: it breaks each score down into its evals.
  // It follows the leaderboard's mode, with a switch of its own so it can be changed from here too.
  function evalsSection() {
    const shown = st.tv === "vanilla" ? E.evals.filter(ev => ev.modes.includes("vanilla")) : E.evals;
    const count = t => shown.filter(ev => ev.type === t).length;
    const types = ["Quiz", "Scenario", "Build", "Act"].filter(count).map(t => `${count(t)} ${t.toLowerCase()}`).join(" · ");
    return `<section class="rsec" id="evals"><div class="rsec-h"><div><h2>Results by eval</h2><p class="rsub">The scores above, broken down: how many runs each agent passed on every eval, grouped by pillar.</p></div><a class="backbtn" href="${REPO}/blob/main/docs/add-an-eval.md" target="_blank" rel="noopener">How to add an eval ↗</a></div>
      <div class="toolbar tvbar">${viewSel()}</div><p class="evcount">${shown.length} evals · ${types}${st.tv === "vanilla" ? " · only the evals with a checkable answer" : ""}</p>${viewMatrix2()}</section>`;
  }

  // ---------- look: clean (the lab report) or geek (a terminal) ----------
  // index.html applies the saved look before the first paint; the switch sits at the right of the nav.
  // Wide screens get both names side by side; phones get one icon button that switches to the other look,
  // like a light/dark toggle: it shows where it takes you, drawn in that look's style (a pixel space invader
  // to geek, a line-drawn briefcase to clean).
  let ui = document.documentElement.dataset.ui === "geek" ? "geek" : "clean";
  const INVADER = ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX", "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."];
  const UI_ICON = {
    geek: `<svg class="ic-invader" viewBox="0 0 11 8" aria-hidden="true">${INVADER.flatMap((row, y) => [...row].map((c, x) => c === "X" ? `<rect x="${x}" y="${y}" width="1" height="1"/>` : "")).join("")}</svg>`,
    clean: `<svg class="ic-case" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="1.5"/><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3 12.5h18M10.5 12.5v1.5h3v-1.5"/></svg>`,
  };
  const otherUi = () => ui === "geek" ? "clean" : "geek";
  const uiSwitch = () => `<span class="uisw" role="group" aria-label="Look">${["clean", "geek"].map(id => `<button data-uiset="${id}" aria-pressed="${ui === id}">${id}</button>`).join("")}</span>`;
  const uiToggle = () => `<button class="uitg" data-uitoggle aria-label="Switch to the ${otherUi()} look" title="Switch to the ${otherUi()} look">${UI_ICON[otherUi()]}</button>`;
  function setUi(next) {
    ui = next; document.documentElement.dataset.ui = next;
    try { localStorage.setItem("ethevals-ui", next); } catch (e) {}
    root.querySelectorAll("[data-uiset]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.uiset === next)));
    root.querySelector(".uitg").outerHTML = uiToggle();
    const y = scrollY; render(false); scrollTo(0, y);
  }

  // ---------- shell ----------
  const NAV = [["results", "Results"], ["how", "How it works"]];
  // The brand carries both marks: the name in text (clean) and the block-letter logo (geek); the look's CSS shows one.
  root.innerHTML = `<nav class="topnav sitenav" aria-label="Site"><a class="brand" href="#/" aria-label="ETH Evals"><span class="brand-txt">ETH Evals</span><span class="brand-logo">${asciiLogo("nlogo-g")}</span></a><span class="navtag">The open benchmark for AI on Ethereum</span><span class="navlinks">${NAV.map(([id, t]) => `<a href="#/${id === "results" ? "" : id}" data-nav="${id}">${t}</a>`).join("")}<a class="gh" href="${REPO}" target="_blank" rel="noopener">GitHub ↗</a>${uiSwitch()}</span>${uiToggle()}</nav>
    <main id="page"></main>
    <footer class="sitefoot"><div><b>ETH Evals</b><span>Open evaluations of AI on Ethereum · <a href="${REPO}" target="_blank" rel="noopener">BuidlGuidl/ethevals</a></span></div><div><span class="canary">${S.canary}</span></div></footer>
    <dialog id="detail" aria-labelledby="detail-title"><div id="detail-content"></div></dialog>`;

  // apply = false reads the route without touching the state (used right after a click changed it).
  function parse(apply = true) {
    const h = location.hash.slice(1) || "/";
    const [path, qs] = h.split("?");
    const q = new URLSearchParams(qs || "");
    if (apply && ["all", ...E.pillars.map(p => p.id)].includes(q.get("pillar"))) st.pillar = q.get("pillar");
    if (apply && ["list", "matrix", "matrix2"].includes(q.get("view"))) st.evView = q.get("view");
    if (apply && ["internet", "skills", "vanilla"].includes(q.get("show"))) st.tv = q.get("show");
    if (apply && ["all", "cost", "read", ...E.pillars.map(p => p.id)].includes(q.get("sort"))) st.sort = q.get("sort");
    const anchor = path.includes("#") ? path.split("#")[1] : "";
    return { parts: path.split("#")[0].split("/").filter(Boolean), anchor };
  }
  const main = () => document.getElementById("page");
  let lastRoute = null;
  const pageKey = () => { const [p, q = ""] = location.hash.split("?"); const qs = new URLSearchParams(q); qs.delete("d"); return p + "?" + qs.toString(); };
  let lastPageKey = null;
  function render(resetScroll = true) {
    if (dialog().open) dialog().close();
    drPushed = false;
    const { parts, anchor } = parse();
    const [a, b] = parts;
    let html, nav = a || "results", title = "";
    if (!a) html = renderReport();
    else if (a === "results") { const [, q = ""] = location.hash.split("?"); location.replace("#/" + (q ? "?" + q : "")); return; }
    else if (a === "benchmarks" || a === "pretraining") { location.replace(a === "pretraining" ? "#/?show=vanilla" : "#/"); return; }
    else if (a === "evals") { const q = new URLSearchParams(location.hash.split("?")[1] || ""); if (["internet", "skills", "vanilla"].includes(q.get("mx"))) st.tv = q.get("mx"); location.replace(evalsHash()); return; }
    else if (a === "how") { html = window.ETHHowItWorks({ repo: REPO }); title = "How it works"; }
    else if (a === "method") { location.replace("#/how#hw-rules"); return; }
    else if (a === "about") { location.replace("#/how"); return; }
    if (html !== undefined) main().innerHTML = html;
    else if (a === "eval") { main().innerHTML = '<div id="main"></div>'; renderEval(decodeURIComponent(b || "")); nav = "results"; title = (evalById(decodeURIComponent(b || "")) || {}).title || ""; }
    else if (a === "run") { main().innerHTML = '<div id="main"></div>'; renderRun(decodeURIComponent(parts.slice(1).join("/"))); nav = "results"; title = "Run"; }
    else if (a === "compare") { main().innerHTML = '<div id="main"></div>'; renderCompare(decodeURIComponent(b || "")); title = "Compare"; }
    else { main().innerHTML = renderReport(); }
    document.title = title ? `${title} · ETH Evals` : "ETH Evals · Open evaluations of AI on Ethereum";
    root.querySelectorAll("[data-nav]").forEach(l => l.toggleAttribute("aria-current", l.dataset.nav === nav));
    const here = parts.join("/");
    if (resetScroll && here !== lastRoute) window.scrollTo(0, 0);
    lastRoute = here;
    if (anchor) document.getElementById(anchor)?.scrollIntoView();
    watchHeroBrand();
    spy();
    lastPageKey = pageKey(); syncD();
  }
  // Results page: the big logo is the brand. The nav's brand and tagline hide while the big logo is on screen;
  // once the nav covers half of it, the big logo flies up into the nav's brand (FLIP: a copy starts at the big
  // logo's place and size and eases into the nav's) while the big one fades. Scrolling back reverses it with a
  // fade. Every other page keeps the brand in the nav.
  let heroObs = null;
  function watchHeroBrand() {
    const nav = root.querySelector(".sitenav"), logo = root.querySelector(".lh-logo");
    heroObs?.disconnect(); heroObs = null;
    if (!logo || !("IntersectionObserver" in window)) { nav.classList.remove("hero-brand"); return; }
    nav.classList.add("hero-brand");
    let first = true;
    heroObs = new IntersectionObserver(([e]) => {
      const inHero = e.intersectionRatio >= .5, was = nav.classList.contains("hero-brand");
      nav.classList.toggle("hero-brand", inHero);
      if (!first && was && !inHero) flyToNav(logo, nav.querySelector(".brand"));
      first = false;
    }, { rootMargin: `-${nav.offsetHeight}px 0px 0px 0px`, threshold: [0, .5, 1] });
    heroObs.observe(logo);
  }
  // The flight is drawn by a copy of the big logo in a fixed layer, so the nav's clipping doesn't cut it.
  // It goes centre to centre and scales by width onto the same mark in the nav: the name in clean (the square
  // fades in with the rest of the brand), the block letters in geek.
  const shown = el => [...el.children].find(c => c.getClientRects().length);
  function flyToNav(logo, brand) {
    const from = shown(logo), to = brand && shown(brand);
    if (!from || !to || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
    if (!a.width || !b.width) return;
    const ghost = from.cloneNode(true);
    ghost.classList.add("logo-ghost");
    Object.assign(ghost.style, { left: a.left + "px", top: a.top + "px", width: a.width + "px", height: a.height + "px" });
    document.body.append(ghost);
    to.style.opacity = "0";
    const dx = b.left + b.width / 2 - (a.left + a.width / 2), dy = b.top + b.height / 2 - (a.top + a.height / 2);
    ghost.animate([{ transform: "none" }, { transform: `translate(${dx}px, ${dy}px) scale(${b.width / a.width})` }],
      { duration: 480, easing: "cubic-bezier(.2, .8, .2, 1)", fill: "forwards" }).finished.finally(() => { to.style.opacity = ""; ghost.remove(); });
  }

  // Changing pillar or mode redraws in place, keeping scroll and focus.
  function rerender(btn, key) {
    const { parts } = parse(false); const [a, b] = parts;
    const q = !a ? reportHash() : `#/${parts.join("/")}?pillar=${st.pillar}`;
    const y = scrollY, top = btn.getBoundingClientRect().top;
    history.replaceState(null, "", q);
    render(false); scrollTo(0, y);
    const el = root.querySelector(key);
    if (el) { scrollTo(0, scrollY + el.getBoundingClientRect().top - top); el.focus({ preventScroll: true }); }
    spy();
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.id === "close-detail") closeD();
    else if (b.dataset.uiset) setUi(b.dataset.uiset);
    else if (b.hasAttribute("data-uitoggle")) { setUi(otherUi()); root.querySelector(".uitg")?.focus(); }
    else if (b.dataset.jump) { const el = document.getElementById(b.dataset.jump); if (el) window.scrollTo({ top: el.getBoundingClientRect().top + scrollY - (document.querySelector(".secbar:not(.flat)") ? 116 : 70), behavior: "smooth" }); }
    else if (b.dataset.tv) { st.tv = b.dataset.tv; rerender(b, `#${b.closest("section").id} [data-tv="${st.tv}"]`); }
    else if (b.dataset.sort) { st.sort = b.dataset.sort; rerender(b, `[data-sort="${st.sort}"]`); }
    else if (b.dataset.evview) { st.evView = b.dataset.evview; rerender(b, `[data-evview="${st.evView}"]`); }
    else if (b.dataset.pillar) { st.pillar = b.dataset.pillar; rerender(b, `[data-pillar="${st.pillar}"]`); }
    else if (b.dataset.open) { const [ag, m, sc] = b.dataset.open.split("~"); openD({ agent: ag, mode: m, scope: sc }, b); }
    else if (b.dataset.evcell) { const [ag, evId] = b.dataset.evcell.split("."); openD({ agent: ag, mode: st.tv, ev: evId }, b); }
    else if (b.dataset.dev) { const [ag, m, evId] = b.dataset.dev.split("~"); openD({ agent: ag, mode: m, ev: evId }, b); }
    else if (b.dataset.dl) goD({ ev: b.dataset.dl, run: 0 });
    else if (b.dataset.drun) goD({ run: +b.dataset.drun });
    else if (b.dataset.dmode) goD({ mode: b.dataset.dmode, run: 0 });
    else if (b.dataset.dgo) goD(b.dataset.dgo === "list" ? { ev: "", run: 0 } : { run: 0 });
    else if (b.dataset.dstep) { const el = document.getElementById("dstep-" + b.dataset.dstep); if (el) { el.closest("details")?.setAttribute("open", ""); document.querySelectorAll(".step.hl").forEach(x => x.classList.remove("hl")); el.classList.add("hl"); el.scrollIntoView({ block: "center", behavior: "smooth" }); } }
  });
  // Runs table rows are clickable too, with the keyboard as well as the mouse.
  document.addEventListener("click", e => { const tr = e.target.closest("tr[data-drun]"); if (tr) goD({ run: +tr.dataset.drun }); });
  document.addEventListener("keydown", e => { const tr = e.target.closest?.("tr[data-drun]"); if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); goD({ run: +tr.dataset.drun }); } });
  dialog().addEventListener("click", e => { if (e.target === dialog()) closeD(); });
  dialog().addEventListener("cancel", e => { e.preventDefault(); closeD(); });
  dialog().addEventListener("close", () => { if (drOpener && document.contains(drOpener)) drOpener.focus({ preventScroll: true }); drOpener = null; });
  // Section nav (Results) and table of contents (Method): mark the section being read.
  // A section is current once its top passes just under the sticky bars; none while the header is in view,
  // and the last one when the page is scrolled to the bottom.
  function spy() {
    const links = [...root.querySelectorAll(".secnav [data-jump], .mtoc [data-jump]")];
    if (!links.length) return;
    const line = (document.querySelector(".secbar:not(.flat)") ? 132 : 90);
    let cur = null;
    links.forEach(l => { const el = document.getElementById(l.dataset.jump); if (el && el.getBoundingClientRect().top - line <= 0) cur = l; });
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) cur = links[links.length - 1];
    links.forEach(l => l.setAttribute("aria-current", String(l === cur)));
  }
  let spyQueued = false;
  addEventListener("scroll", () => { if (!spyQueued) { spyQueued = true; requestAnimationFrame(() => { spyQueued = false; spy(); }); } }, { passive: true });
  addEventListener("resize", spy);
  // The panel lives in ?d=; a change there alone (opening, Back) does not re-render the page behind it.
  addEventListener("hashchange", () => { if (pageKey() === lastPageKey) syncD(); else render(); });
  render();
})();
