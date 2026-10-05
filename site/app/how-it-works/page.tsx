import Link from "next/link";
import { FileText, ShieldCheck, GitMerge, Terminal, GitPullRequest, Table2, Bot, Scale, Check } from "lucide-react";
import { loadBoard } from "../../src/load";
import { pillars } from "../../src/board";
import { names } from "../../src/labels";
import { PipelineDiagram, RunDiagram } from "../../components/diagrams";

export const metadata = { title: "How it works · ETH Evals" };
const inspect = "https://inspect.aisi.org.uk/", hf = "https://huggingface.co/datasets/buidlguidl/ethevals-test";
const scope = {
  concepts: "How the protocol works: finality, gas and fees, L2s, ERCs and EIPs, wallets and keys.",
  transactions: "Acting on chain: encoding calldata and signatures, reading live state, sending transfers and swaps.",
  building: "Code that has to work: contracts from a spec, test suites, repairing a project, wallet flows in a frontend.",
  security: "Vulnerabilities: spotting known bug patterns, triaging an audit, fixing a bug before it ships.",
};
const examples = { concepts: "concepts/agent-registries", transactions: "transactions/send-six-decimal-token", building: "building/erc20-points-token", security: null };
const runNotes = [
  { icon: Bot, title: "The agent works.", body: "It gets only the prompt and its workspace, and sends the transfer on its private chain." },
  { icon: ShieldCheck, title: "The scorer verifies.", body: "When the agent stops, the scorer reads the chain: did exactly 12.5 tokens arrive?" },
  { icon: Scale, title: "An LLM judges the process.", body: "The runner hands it the transcript: did the agent check the transfer landed before saying it was done?" },
  { icon: Check, title: "Results + logs.", body: "The scorer's checks and the judge's answers become one result on the website, one click from the full log." },
];
const pipelineNotes = [
  { icon: FileText, title: "Add an eval or a model.", body: <>An eval is a folder: the prompt, the files the agent starts with, and how it is scored. A new model is one entry in <code>config.yaml</code>.</> },
  { icon: ShieldCheck, title: "PR: validity checks.", body: "Before any real model runs, the eval is checked with a mock model: the reference solution must pass and an untouched workspace must fail." },
  { icon: GitMerge, title: "Merge to main.", body: "A maintainer reads the eval and how it is graded, then merges." },
  { icon: Terminal, title: "CI runs only what's new.", body: "CI runs every agent and model on the evals they have no result for yet." },
  { icon: GitPullRequest, title: "Results PR.", body: "CI opens a pull request with the new results. The full logs go to a GitHub release." },
  { icon: Table2, title: "Merge → website.", body: "Merging it rebuilds the site. Every result links to its checks and full log." },
];

export default function Page() {
  const data = loadBoard(), evaluations = Object.values(data.evaluations);
  return <main id="main" className="page how-page">
    <header className="how-hero"><h1>Automated, open evals for AI on Ethereum</h1><p className="lead">Experts add evals by pull request. After review, CI runs them on every agent and model, grades each run, and publishes the results with their full logs. No step needs anyone to copy a number by hand.</p></header>
    <section id="hw-pipe" className="how-section"><div className="how-head"><p className="eyebrow">The pipeline</p><h2>One pull request starts everything</h2></div>
      <figure className="diagram-figure"><PipelineDiagram /><ol className="diagram-notes pipeline-notes">{pipelineNotes.map(({ icon: Icon, title, body }, index) => <li key={title} className={index >= 3 ? "automatic" : ""}><span className="note-icon"><Icon size={20} /></span><h3>{title}</h3><p>{body}</p></li>)}</ol>
        <figcaption>On every merge, the model-only evals with a fixed answer are also published as a <a href={hf}>Hugging Face dataset</a>, ready to run in <a href={inspect}>Inspect</a>.</figcaption></figure>
    </section>
    <section id="hw-pillars" className="how-section"><div className="how-head"><p className="eyebrow">What we measure</p><h2>Four pillars</h2>
      <p>Each eval tests one of these four areas of Ethereum work.</p></div>
      <ol className="pillars-grid">{pillars.map((pillar) => {
        const count = evaluations.filter((ev) => ev.pillar === pillar).length, example = examples[pillar];
        return <li key={pillar}><h3>{names[pillar]}</h3><span className="eyebrow">{count ? `${count} ${count === 1 ? "eval" : "evals"}` : "No evals yet"}</span><p>{scope[pillar]}</p>
          {example && data.evaluations[example] ? <Link className="pillar-example" href={`/#eval-${example.replaceAll("/", "-")}`}>{example} →</Link> : <span className="pillar-example muted">No evals yet</span>}</li>;
      })}</ol>
    </section>
    <section id="hw-modes" className="how-section"><div className="how-head"><p className="eyebrow">Modes</p><h2>Three ways to run an eval</h2></div>
      <div className="modes-grid"><article className="model-only"><p className="eyebrow">Model only</p><h3>What does the model know?</h3><p>The bare model answers in one API call, with no tools, no web and no workspace. Only evals with a fixed answer run this way.</p></article>
        <article><p className="eyebrow">Internet</p><h3>Can an agent do the work?</h3><p>A coding agent works the way it normally would, with a shell, the web, its workspace, and a private chain when the task needs one.</p></article>
        <article><p className="eyebrow">Internet + Skills</p><h3>Do Ethereum&apos;s own guides help?</h3><p>The same agent and setup, plus a pinned pack of <a href="https://ethskills.com">ethskills</a> guides. The gap between the two modes is the skill lift on the website.</p></article></div>
    </section>
    <section id="hw-run" className="how-section"><div className="how-head"><p className="eyebrow">Inside one run</p><h2>One task, start to finish</h2>
      <p>Take one Transactions eval: &quot;send 12.5 tokens to the recipient.&quot; Here is what happens.</p></div>
      <figure className="diagram-figure"><RunDiagram /><ol className="diagram-notes run-notes">{runNotes.map(({ icon: Icon, title, body }) => <li key={title}><span className="note-icon"><Icon size={20} /></span><h3>{title}</h3><p>{body}</p></li>)}</ol></figure>
      <p><a href={inspect}>Inspect</a>, the UK AI Security Institute&apos;s open-source eval framework, runs every eval and keeps the full log.</p>
      <div className="rules"><h3>Rules every run follows</h3><ul>
        <li><b>The agent only gets the task.</b> The prompt and its workspace; the scorer runs in its own container the agent can&apos;t reach.</li>
        <li><b>No shortcuts on the chain.</b> Cheat codes, like setting a balance by hand, are blocked, so the agent can&apos;t fake a result.</li>
        <li><b>Judging starts after the agent stops.</b> The scorer and the LLM judge only look once the agent is done.</li>
        <li><b>Results stay tied to what made them.</b> Change the eval, the model or the agent, and it runs again.</li>
      </ul></div>
    </section>
    <section id="hw-stack" className="how-section"><div className="how-head"><p className="eyebrow">Under the hood</p><h2>What it runs on</h2></div><ul className="stack-list">
      <li><b><a href={inspect}>Inspect</a></b> runs every eval and records each run as a log anyone can open. It is the open-source evaluation framework from the UK AI Security Institute.</li>
      <li><b>Agents:</b> Claude Code, Codex CLI and OpenCode, each in a fresh Docker sandbox for every run.</li>
      <li><b>Models</b> are called through Anthropic&apos;s and OpenAI&apos;s own APIs, and open models through OpenRouter.</li>
      <li><b>Foundry:</b> Forge runs the tests, and Anvil runs a private chain or a mainnet fork.</li>
      <li><b>Skills:</b> a pinned pack of four <a href="https://ethskills.com">ethskills</a> guides, which the agent reads in Internet + Skills mode.</li>
      <li><b>Results</b> are rows in the repository. The full logs are GitHub release assets.</li>
      <li><b>Dataset:</b> the model-only evals with a fixed answer are a <a href={hf}>Hugging Face dataset</a>, ready to run in Inspect.</li>
    </ul></section>
    <section id="hw-add" className="how-add"><p>Have an Ethereum task AI should handle? Add it as an eval.</p><a className="button" href="https://github.com/BuidlGuidl/ethevals/blob/main/docs/add-an-eval.md">Read the guide →</a></section>
  </main>;
}
