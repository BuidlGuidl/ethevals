import { pillars } from "../../src/board";
import { names } from "../../src/labels";
import { PipelineDiagram, RunDiagram } from "../../components/diagrams";

export const metadata = { title: "How it works · ETH Evals" };
const scope = {
  concepts: "How the protocol works: finality, gas and fees, L2s, ERCs and EIPs, wallets and keys.",
  transactions: "Acting on chain: encoding calldata and signatures, reading live state, sending transfers and swaps.",
  building: "Code that has to work: contracts from a spec, test suites, repairing a project, wallet flows in a frontend.",
  security: "Vulnerabilities: spotting known bug patterns, triaging an audit, fixing a bug before it ships.",
};
const evalFiles = [
  ["├──", "task.toml", "settings, motivation, and modes"],
  ["├──", "instruction.md", "the instruction the agent receives"],
  ["├──", "environment/", ""],
  ["│   ├──", "Dockerfile", "the agent's tools and starting files"],
  ["│   └──", "docker-compose.yaml", "optional sidecars, such as a chain"],
  ["├──", "tests/", ""],
  ["│   ├──", "test.sh", "the verifier that writes named checks"],
  ["│   └──", "criteria.md", "optional questions for a judge"],
  ["└──", "solution/", "solve.sh, which the oracle runs"],
];

export default function Page() {
  return <main id="main" className="page how-page">
    <header className="how-hero"><h1>Automated, open tasks for AI on Ethereum</h1><p className="lead">Experts add tasks by pull request. After review, an automated pipeline runs them on every agent and model, checks each trial, and publishes the results with their full trajectories.</p></header>
    <section id="hw-pipe" className="how-section"><div className="how-head"><p className="eyebrow">The pipeline</p><h2>One pull request starts everything</h2>
      <p>A new model is one line of config, so it can be tested the day it launches. A new or changed task runs on every agent and model as soon as it merges.</p></div>
      <figure className="diagram-figure"><PipelineDiagram /></figure>
    </section>
    <section id="hw-pillars" className="how-section"><div className="how-head"><p className="eyebrow">What we measure</p><h2>Four pillars</h2>
      <p>Each task tests one of these four areas of Ethereum work.</p></div>
      <ol className="pillars-grid">{pillars.map((pillar) => <li key={pillar}><h3>{names[pillar]}</h3><p>{scope[pillar]}</p></li>)}</ol>
      <div className="how-modes"><h3>Three ways to run a task</h3>
        <div className="modes-grid"><article className="model-only"><p className="eyebrow">Model only</p><h3>What does the model know?</h3><p>The bare model answers in one API call, with no tools or web.</p></article>
          <article><p className="eyebrow">Internet</p><h3>Can an agent do the work?</h3><p>A coding agent with a shell, the web, and its own chain when the task needs one.</p></article>
          <article><p className="eyebrow">Internet + Skills</p><h3>Do Ethereum&apos;s own guides help?</h3><p>The same agent, plus a pack of <a href="https://ethskills.com">ethskills</a> guides. The difference between the two is the skill lift.</p></article></div>
      </div>
    </section>
    <section id="hw-eval" className="how-section"><div className="how-head"><p className="eyebrow">Inside a task</p><h2>A task is a folder</h2>
      <p>Each Harbor task declares its instruction, environment, verifier, and solution.</p></div>
      <div className="eval-tree" aria-label="Task folder contents"><div className="eval-tree-root">tasks/&lt;pillar&gt;/&lt;name&gt;/</div>
        <ul>{evalFiles.map(([branch, name, comment]) => <li key={name} className={[
          branch.startsWith("│") ? "eval-tree-child" : "",
          branch.startsWith("│") && branch.includes("└") ? "eval-tree-child-last" : "",
          name === "environment/" || name === "tests/" ? "eval-tree-parent" : "",
        ].filter(Boolean).join(" ")}>
          <span className="eval-tree-file"><span className="eval-tree-branch" aria-hidden="true">{branch} </span>{name}</span>
          {comment && <span className="eval-tree-comment"># {comment}</span>}
        </li>)}</ul>
      </div>
      <p className="how-intro">Chain setup is a Forge script and the tests are Forge tests, so an Ethereum developer writes them the way they already work.</p>
    </section>
    <section id="hw-run" className="how-section"><div className="how-head"><p className="eyebrow">Inside one trial</p><h2>One task, start to finish</h2>
      <p>Take one Transactions task: &quot;send tokens to the recipient.&quot; Here is what happens.</p></div>
      <figure className="diagram-figure"><RunDiagram /></figure>
      <div className="rules"><h3>Rules every trial follows</h3><ul>
        <li><b>Tests arrive after the agent stops.</b> Harbor starts a separate verifier, or checks a live sidecar in the agent&apos;s container.</li>
        <li><b>No shortcuts on the chain.</b> Chain controls, like setting a balance by hand, are blocked by the RPC filter.</li>
        <li><b>Judging starts after the agent stops.</b> The verifier and the LLM judge only look once the agent is done.</li>
        <li><b>Results stay tied to what made them.</b> Change the task, the model or the agent, and it runs again.</li>
      </ul></div>
    </section>
    <section id="hw-add" className="how-add"><p>Have an Ethereum task AI should handle? Add it as a task.</p><a className="button" href="https://github.com/BuidlGuidl/ethevals/blob/main/docs/add-a-task.md">Read the guide →</a></section>
  </main>;
}
