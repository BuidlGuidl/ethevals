/* How it works: one page shared by site/ and site-simple/.
   The pipeline diagram redraws Shiv's "big picture" from the ETHEvals system walkthrough (Loom, 1 Oct 2026);
   details follow BuidlGuidl/ethevals: docs/add-an-eval.md, docs/adr/, .github/workflows/. */
(function () {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const paths = {
    eval: '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h4"/>',
    model: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    checks: '<path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="m9 12 2 2 4-4"/>',
    merge: '<circle cx="6" cy="5" r="2.2"/><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="12" r="2.2"/><path d="M6 7.2v9.6M6 9c0 3 3 3 9.8 3"/>',
    run: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m8 10 3 2.5L8 15M13 15h3"/>',
    pr: '<circle cx="6" cy="5" r="2.2"/><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="19" r="2.2"/><path d="M6 7.2v9.6M18 16.8V9a3 3 0 0 0-3-3h-4m2-2.5L10.5 6 13 8.5"/>',
    board: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M9 9v11M14 9v11"/>',
    dataset: '<ellipse cx="12" cy="5.5" rx="8" ry="2.8"/><path d="M4 5.5v13c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8v-13M4 12c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8"/>',
    agent: '<rect x="4" y="8" width="16" height="11" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01M10 16h4"/>',
    chain: '<path d="M12 2 4 7v10l8 5 8-5V7z"/><path d="m4 7 8 5 8-5M12 12v10"/>',
    judge: '<path d="M12 3v18M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0zM8 21h8"/>',
    prompt: '<path d="M4 5h16v11H9l-5 4z"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6"/>',
    log: '<path d="M5 3h10l4 4v14H5z"/><path d="M9 9h6M9 13h6M9 17h3"/>',
  };
  const icon = k => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${paths[k]}</svg>`;

  // ---------- The pipeline (Shiv's big picture) ----------
  // kind: the phase colour (neutral for phases 1–2, blue for the automatic phase 3). Content matches his boxes; sub-lines only spell them out.
  const W = 180, H = 108, X = i => 20 + i * 220;
  const nodes = [
    { id: "eval", x: X(0), y: 84, kind: "phase", icon: "eval", t: "Add or edit an eval", s: ["a folder: prompt, files", "and how it is scored"] },
    { id: "model", x: X(0), y: 246, kind: "phase", icon: "model", t: "New model", s: ["one entry in", "config.yaml"] },
    { id: "checks", x: X(1), y: 165, kind: "phase", icon: "checks", t: "PR: free checks", s: ["prove the eval works,", "no API keys spent"] },
    { id: "merge", x: X(2), y: 165, kind: "phase", icon: "merge", t: "Merge to main", s: ["a maintainer reviews", "and merges"] },
    { id: "run", x: X(3), y: 66, kind: "auto", icon: "run", t: "CI runs missing epochs", s: ["only what has no", "result yet, on budget"] },
    { id: "pr", x: X(4), y: 66, kind: "auto", icon: "pr", t: "Results PR", s: ["rows + Inspect logs", "as release assets"] },
    { id: "board", x: X(5), y: 66, kind: "dest", icon: "board", t: "Merge → board", s: ["the leaderboard", "updates"] },
    { id: "hf", x: X(3), y: 264, kind: "auto", icon: "dataset", t: "Publish HF dataset", s: ["quiz evals →", "Hugging Face"] },
  ];
  const cy = id => { const n = nodes.find(m => m.id === id); return n.y + H / 2; };
  const r = 8; // corner radius of connector bends
  const elbow = (x1, y1, xm, y2, x2) => {
    const dir = y2 > y1 ? 1 : -1;
    return `M${x1} ${y1}H${xm - r}Q${xm} ${y1} ${xm} ${y1 + dir * r}V${y2 - dir * r}Q${xm} ${y2} ${xm + r} ${y2}H${x2}`;
  };
  const edges = [
    ["phase", elbow(X(0) + W, cy("eval"), X(1) - 20, cy("checks"), X(1) - 3)],
    ["phase", elbow(X(0) + W, cy("model"), X(1) - 20, cy("checks"), X(1) - 3)],
    ["phase", `M${X(1) + W} ${cy("checks")}H${X(2) - 3}`],
    ["auto", elbow(X(2) + W, cy("merge"), X(3) - 20, cy("run"), X(3) - 3), "on merge"],
    ["auto", elbow(X(2) + W, cy("merge"), X(3) - 20, cy("hf"), X(3) - 3)],
    ["auto", `M${X(3) + W} ${cy("run")}H${X(4) - 3}`],
    ["auto", `M${X(4) + W} ${cy("pr")}H${X(5) - 3}`],
  ];
  function node(n) {
    const sub = n.s.map((s, i) => `<text class="bp-sub" x="${n.x + 18}" y="${n.y + 84 + i * 17}">${esc(s)}</text>`).join("");
    return `<g class="bp-node ${n.kind}"><rect class="bp-box" x="${n.x}" y="${n.y}" width="${W}" height="${H}" rx="10"/>
      <g class="bp-ic" transform="translate(${n.x + 16} ${n.y + 15}) scale(.95)">${paths[n.icon]}</g>
      <text class="bp-t" x="${n.x + 18}" y="${n.y + 62}">${esc(n.t)}</text>${sub}</g>`;
  }
  const zones = [["1 · Contribute", X(0), X(0) + W, "phase"], ["2 · Review", X(1), X(2) + W, "phase"], ["3 · Automatic on main", X(3), X(5) + W, "auto"]];
  const pipeline = () => `<svg class="bp" viewBox="0 0 1320 400" role="img" aria-labelledby="bp-t bp-d">
      <title id="bp-t">The ETH Evals pipeline</title>
      <desc id="bp-d">An author adds or edits an eval, or adds a new model in config.yaml. The pull request runs free checks, then a maintainer merges it to main. On merge, CI runs only the missing epochs and opens a results pull request with result rows and Inspect logs as GitHub release assets. Merging it updates the leaderboard. In parallel, quiz evals are published to Hugging Face.</desc>
      <defs>${["phase", "auto"].map(k => `<marker id="bp-ar-${k}" class="bp-mk ${k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M1.5 1.5 8.5 5 1.5 8.5"/></marker>`).join("")}</defs>
      ${zones.map(([l, a, b, k]) => `<g class="bp-zone ${k}"><path d="M${a} 34H${b}"/><text x="${a}" y="22">${esc(l)}</text></g>`).join("")}
      ${edges.map(([k, d, label], i) => `<g class="bp-edge ${k}"><path d="${d}" marker-end="url(#bp-ar-${k})"/><path class="bp-pulse" d="${d}" pathLength="100" style="animation-delay:${(i * .45).toFixed(2)}s"/></g>`).join("")}
      ${nodes.map(node).join("")}
    </svg>`;

  const ext = (href, text) => `<a href="${href}" target="_blank" rel="noopener">${text}</a>`;
  const TOOL = {
    inspect: "https://inspect.aisi.org.uk/", claudeCode: "https://github.com/anthropics/claude-code", codex: "https://github.com/openai/codex",
    opencode: "https://opencode.ai", openrouter: "https://openrouter.ai", foundry: "https://getfoundry.sh", ethskills: "https://ethskills.com",
    hf: "https://huggingface.co/datasets/buidlguidl/ethevals-test",
  };

  // Step notes sit under the diagram, one per column; on phones they become the diagram.
  const notes = repo => [
    ["eval", "phase", "Add an eval or a model", `An eval is a folder: the prompt, the files the agent starts with, and how it is scored. A new model is one entry in ${ext(`${repo}/blob/main/inspect-runner/ethevals/config.yaml`, "<code>config.yaml</code>")}.`],
    ["checks", "phase", "PR: free checks", "The reference solution must pass and an empty answer must fail. No API calls, so anyone can open a PR from a fork."],
    ["merge", "phase", "Merge to main", "A maintainer reads the eval and its grading rubric, then merges."],
    ["run", "auto", "CI runs missing epochs", "CI runs every agent and model on the evals they have no result for yet, within a set budget."],
    ["pr", "auto", "Results PR", "CI returns the result rows as a pull request. The full Inspect logs go to a GitHub release."],
    ["board", "dest", "Merge → board", "Merging it rebuilds the site. Every cell links to its checks and full log."],
  ];

  // ---------- One run ----------
  const flowStep = (ic, h, p, cls = "") => `<div class="hw-fs ${cls}"><span class="hw-fi">${icon(ic)}</span><div><b>${h}</b><span>${p}</span></div></div>`;
  const arrow = '<span class="hw-fa" aria-hidden="true"></span>';
  // One card per eval type: what it gets, who does the work, what is checked.
  const MODE = { vanilla: "Model only", internet: "Internet", skills: "+ Skills" };
  const modes = ms => `<span class="hw-modes">${ms.map(m => `<i class="${m}">${MODE[m]}</i>`).join("")}</span>`;
  const card = (type, does, ms, body) => `<div class="hw-run"><div class="hw-run-h"><b>${type}</b>${modes(ms)}</div><p class="hw-run-d">${does}</p>${body}</div>`;
  const runs = () => `<div class="hw-runs">
      ${card("Quiz", "Tests what a model or agent knows. It answers a question that has one fixed answer, checked deterministically. It is also the only type a model can answer without an agent, because it needs no tools.", ["vanilla", "internet", "skills"], `
        ${flowStep("prompt", "Question", "“Which ERC defines on-chain registries for AI agents? Reply with just the number.”")}${arrow}
        ${flowStep("agent", "Model or agent", "Either can answer: the model alone in one API call, with no tools and web search off, or an agent in its sandbox with the web.")}${arrow}
        ${flowStep("target", "Deterministic match", "The reply must match the expected answer, 8004: exactly, by pattern or as a multiple-choice letter.")}`)}
      ${card("Build", "Tests whether an agent can write working code. It finishes or fixes a project in its workspace, and tests it never sees decide the result.", ["internet", "skills"], `
        ${flowStep("prompt", "Prompt + starter code", "For example: finish an ERC-20 points token in <code>src/</code>.")}${arrow}
        <div class="hw-sandbox"><span class="hw-sb-k">Fresh Docker sandbox</span>
          ${flowStep("agent", "Agent writes the code", `Claude Code, Codex or OpenCode, with ${ext(TOOL.foundry, "Foundry")} and internet.`)}</div>${arrow}
        ${flowStep("checks", "Forge tests", "Tests kept out of its workspace run on its code. It must compile and pass them all.")}`)}
      ${card("Act", "Tests whether an agent can operate on Ethereum. It sends transactions on a private chain, and a script checks the state they leave behind.", ["internet", "skills"], `
        ${flowStep("prompt", "Prompt + chain details", "“Send exactly 12.5 tokens”, with an RPC URL and a funded key.")}${arrow}
        <div class="hw-sandbox"><span class="hw-sb-k">Fresh Docker sandbox</span>
          ${flowStep("agent", "Agent", "Signs transactions with its key.")}
          <span class="hw-fa sm" aria-hidden="true"><i>filtered RPC</i></span>
          ${flowStep("chain", "Private Ethereum chain", "Its own container. Chain controls are blocked.")}</div>${arrow}
        ${flowStep("chain", "Script reads the chain", "Recipient got 12,500,000 units (6 decimals); one transaction, from the agent’s key.")}
        <div class="hw-plus-j">${flowStep("judge", "AI judge reads the transcript", "Did it confirm the transfer before reporting?")}</div>`)}
    </div>
    <p class="hw-run-note">Each eval declares the modes it runs in, and a run passes only if every check passes. Internet + Skills also gives the agent Ethereum skills to read, such as ${ext(TOOL.ethskills, "ethskills")}. Any eval can also add an <b>AI judge</b>: yes-or-no questions a grader model answers from the transcript, or from the code for builds.</p>`;

  window.ETHHowItWorks = function ({ repo }) {
    return `<div class="page hw">
      <header class="hw-hero"><h1>Automated, open evals for AI on Ethereum</h1>
        <p class="lead">Experts add evals by pull request. After review, CI runs them on every agent and model, grades each run, and publishes the results with their full logs. No step needs anyone to copy a number by hand.</p></header>

      <section class="hw-sec" aria-labelledby="hw-pipe">
        <div class="hw-head"><p class="eyebrow">The pipeline</p><h2 id="hw-pipe">One pull request starts everything</h2></div>
        <figure class="hw-bp">${pipeline()}
          <ol class="hw-notes">${notes(repo).map(([ic, k, h, p]) => `<li class="${k}"><span class="hw-ni">${icon(ic)}</span><h3>${h}</h3><p>${p}</p></li>`).join("")}</ol>
          <figcaption><span class="hw-plus">${icon("dataset")}</span><span>On every merge, the quiz evals are also published as a ${ext(TOOL.hf, "<b>Hugging Face dataset</b>")}, ready to load in ${ext(TOOL.inspect, "Inspect")}.</span></figcaption></figure>
      </section>

      <section class="hw-sec" aria-labelledby="hw-one">
        <div class="hw-head"><p class="eyebrow">Eval types</p><h2 id="hw-one">Answer, build or act</h2><p class="hw-sub">Every eval is one of three types. The type sets what the agent starts with, what it has to do and how its work is graded, and the tags show which modes it runs in. A fourth type, <b>Scenario</b>, is on the way: the agent reviews a situation and writes up what it finds.</p></div>
        ${runs()}
      </section>

      <div class="hw-two">
        <section class="hw-sec" aria-labelledby="hw-stack">
          <div class="hw-head"><p class="eyebrow">Under the hood</p><h2 id="hw-stack">What it runs on</h2></div>
          <ul class="hw-list">
            <li><b>${ext(TOOL.inspect, "Inspect")}</b> runs every eval and records each run as a log anyone can open. It is the evaluation framework from the UK AI Security Institute.</li>
            <li><b>Agents:</b> ${ext(TOOL.claudeCode, "Claude Code")}, ${ext(TOOL.codex, "Codex")} and ${ext(TOOL.opencode, "OpenCode")}, each in a fresh Docker sandbox.</li>
            <li><b>Models</b> are called through Anthropic's and OpenAI's own APIs, and open models through ${ext(TOOL.openrouter, "OpenRouter")}.</li>
            <li><b>${ext(TOOL.foundry, "Foundry")}</b> compiles and tests the code agents write, and runs the private chain for act evals.</li>
            <li><b>Skills</b> are Ethereum guides the agent can read in Internet + Skills mode, such as ${ext(TOOL.ethskills, "ethskills")}.</li>
            <li><b>Results</b> are ${ext(`${repo}/blob/main/results/rows.jsonl`, "rows in the repository")}; the full logs are ${ext(`${repo}/releases`, "GitHub release assets")}.</li>
            <li><b>The quiz evals</b> are a ${ext(TOOL.hf, "Hugging Face dataset")}, ready to run in Inspect.</li>
          </ul>
        </section>

        <section class="hw-sec" aria-labelledby="hw-rules">
          <div class="hw-head"><p class="eyebrow">Fair play</p><h2 id="hw-rules">Rules every run follows</h2></div>
          <ul class="hw-list">
            <li><b>The agent sees only the task.</b> Tests, setup scripts and the scorer stay outside its sandbox.</li>
            <li><b>No shortcuts on the chain.</b> Methods such as <code>anvil_setBalance</code> are blocked, so an agent can't fake a result.</li>
            <li><b>Grading is a separate step.</b> Rubric questions go to a grader model in its own call, after the agent finishes.</li>
            <li><b>A changed eval starts over.</b> Editing an eval drops its old results, and CI runs it again.</li>
            <li><b>Errors don't count against an agent.</b> A run that fails to complete, such as a crash or a provider outage, stays visible but is left out of the score.</li>
            <li><b>Possible contamination is flagged</b> when an eval was published before the model's training cutoff.</li>
          </ul>
        </section>
      </div></div>`;
  };
})();
