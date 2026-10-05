import { FileText, Cpu, ShieldCheck, GitMerge, Terminal, GitPullRequest, Table2, Database, Bot, Box, Scale, type LucideIcon } from "lucide-react";

type Node = { id: string; x: number; y: number; width?: number; height?: number; title: string; titleLines?: string[]; lines: string[]; icon: LucideIcon; kind?: "auto" | "dest"; container?: boolean; files?: string[]; note?: string; noteLines?: string[] };
function DiagramNode({ node }: { node: Node }) {
  const Icon = node.icon;
  return <g className={`diagram-node ${node.kind ?? "phase"}${node.container ? " container" : ""}`} aria-label={node.title}>
    <rect className="diagram-box" x={node.x} y={node.y} width={node.width ?? 180} height={node.height ?? 108} rx="10" />
    <Icon className="diagram-icon" x={node.x + 16} y={node.y + 15} width={24} height={24} strokeWidth={1.6} />
    {node.container && <g className="container-tag"><rect x={node.x + (node.width ?? 180) - 92} y={node.y + 15} width="74" height="22" rx="4" />
      <text x={node.x + (node.width ?? 180) - 55} y={node.y + 30} textAnchor="middle">container</text></g>}
    <text className="diagram-title" x={node.x + 18} y={node.y + 62}>{node.titleLines ? node.titleLines.map((line, i) => <tspan key={line} x={node.x + 18} dy={i ? 17 : 0}>{line}{i < node.titleLines!.length - 1 ? " " : ""}</tspan>) : node.title}</text>
    {node.lines.map((line, i) => <text key={i} className="diagram-sub" x={node.x + 18} y={node.y + 84 + ((node.titleLines?.length ?? 1) - 1) * 17 + i * 17}>{line}</text>)}
    {node.files?.map((file, i) => <g key={file}><FileText className="diagram-icon" x={node.x + 18} y={node.y + 107 + i * 23} width="14" height="14" strokeWidth={1.6} />
      <text className="diagram-file" x={node.x + 40} y={node.y + 119 + i * 23}>{file}</text></g>)}
    {node.note && <text className="diagram-sub diagram-dim" x={node.x + 18} y={node.y + 171}>{node.noteLines ? node.noteLines.map((line, i) => <tspan key={line} x={node.x + 18} dy={i ? 18 : 0}>{line}{i < node.noteLines!.length - 1 ? " " : ""}</tspan>) : node.note}</text>}
  </g>;
}
function Arrows({ id }: { id: string }) {
  return <defs>{["phase", "auto"].map((kind) => <marker key={kind} id={`${id}-${kind}`} className={`diagram-marker ${kind}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M1.5 1.5 8.5 5 1.5 8.5" /></marker>)}</defs>;
}
function Edge({ d, kind = "auto", id, index = 0, arrow = true }: { d: string; kind?: string; id: string; index?: number; arrow?: boolean }) {
  return <g className={`diagram-edge ${kind}`}><path d={d} markerEnd={arrow ? `url(#${id}-${kind})` : undefined} />
    <path className="diagram-pulse" d={d} pathLength="100" style={{ animationDelay: `${index * .45}s` }} /></g>;
}
function elbow(x1: number, y1: number, middle: number, y2: number, x2: number) {
  const r = 8, dir = y2 > y1 ? 1 : -1;
  return `M${x1} ${y1}H${middle-r}Q${middle} ${y1} ${middle} ${y1+dir*r}V${y2-dir*r}Q${middle} ${y2} ${middle+r} ${y2}H${x2}`;
}

function PipelineLayout({ mobile = false }: { mobile?: boolean }) {
  const nodes: Node[] = [
    { id: "eval", x: 20, y: 84, title: "Add or edit an eval", lines: ["a folder: prompt, files, scoring"], icon: FileText },
    { id: "model", x: 20, y: 246, title: "Add a model", lines: ["one entry in config.yaml"], icon: Cpu },
    { id: "checks", x: 240, y: 165, title: "PR: validity checks", lines: ["checked with a mock model"], icon: ShieldCheck },
    { id: "merge", x: 460, y: 165, title: "Merge to main", lines: ["a maintainer reviews"], icon: GitMerge },
    { id: "ci", x: 680, y: 66, title: "CI runs only what's new", lines: ["every agent and model"], icon: Terminal, kind: "auto" },
    { id: "pr", x: 900, y: 66, title: "Results PR", lines: ["results + logs"], icon: GitPullRequest, kind: "auto" },
    { id: "website", x: 1120, y: 66, title: "Merge → website", lines: ["the board updates"], icon: Table2, kind: "dest" },
    { id: "hf", x: 680, y: 264, height: 125, title: "Publish Hugging Face dataset", titleLines: ["Publish Hugging Face", "dataset"], lines: ["model-only evals"], icon: Database, kind: "auto" },
  ];
  const edges = [
    ["phase", elbow(200, 138, 220, 219, 237)], ["phase", elbow(200, 300, 220, 219, 237)], ["phase", "M420 219H457"],
    ["auto", elbow(640, 219, 660, 120, 677)], ["auto", elbow(640, 219, 660, 318, 677)],
    ["auto", "M860 120H897"], ["auto", "M1080 120H1117"],
  ];
  const variant = mobile ? "phone" : "desktop", id = `pipeline-${variant}`;
  const phoneNodes: Node[] = [
    ...[60, 200, 430, 580, 820, 970, 1120].map((y, index) => ({ ...nodes[index], x: 55, y, width: 260 })),
    { ...nodes[7], x: 55, y: 1320, width: 260, height: 108, titleLines: undefined },
  ];
  const phoneEdges = [
    ["phase", "M55 114H25V344"], ["phase", "M185 308V344H25"], ["phase", "M25 344V484H52"],
    ["phase", "M185 538V577"], ["auto", "M55 634H25V1374H52"],
    // The main line pauses at the stage heading so it crosses neither text nor rule.
    ["auto", "M185 688V710"], ["auto", "M185 780V817"],
    ["auto", "M185 928V967"], ["auto", "M185 1078V1117"],
  ];
  return <svg className={`diagram pipeline-diagram diagram-${variant}`} viewBox={mobile ? "0 0 345 1460" : "0 0 1320 400"} role="img" aria-labelledby={`${id}-title ${id}-desc`}>
    <title id={`${id}-title`}>From pull request to website</title><desc id={`${id}-desc`}>Eval and model pull requests pass validity checks with a mock model and maintainer review. After merge, CI runs new epochs for every agent and model. A results pull request updates the website. Model-only evals also go to Hugging Face.</desc>
    <Arrows id={id} />
    {[["1 · Contribute", 20, 200], ["2 · Review", 240, 640], ["3 · Automatic on main", 680, 1300]].map(([label, start, end], index) => <g key={label} className={`diagram-zone ${index === 2 ? "auto" : "phase"}`}><path d={mobile ? `M55 ${[34, 396, 756][index]}H315` : `M${start} 34H${end}`} /><text x={mobile ? 55 : start} y={mobile ? [22, 382, 742][index] : 22}>{label}</text></g>)}
    {(mobile ? phoneEdges : edges).map(([kind, d], index) => <Edge key={index} d={d} kind={kind} id={id} index={index} arrow={!mobile || (index > 1 && index !== 5)} />)}
    {(mobile ? phoneNodes : nodes).map((node) => <DiagramNode key={node.id} node={node} />)}
  </svg>;
}

export function PipelineDiagram() {
  return <><PipelineLayout /><PipelineLayout mobile /></>;
}

function RunStep({ x, y, width, height = 100, title, lines = [] }: { x: number; y: number; width: number; height?: number; title: string; lines?: string[] }) {
  return <g className="diagram-node">
    <rect className="diagram-box" x={x} y={y} width={width} height={height} rx="10" />
    <text className="diagram-title" x={x + 18} y={y + 32}>{title}</text>
    {lines.length > 0 && <text className="diagram-sub" x={x + 18} y={y + 58}>{lines.map((line, i) => <tspan key={line} x={x + 18} dy={i ? 18 : 0}>{line}{i < lines.length - 1 ? " " : ""}</tspan>)}</text>}
  </g>;
}

function RunLayout({ mobile = false }: { mobile?: boolean }) {
  const variant = mobile ? "phone" : "desktop", id = "run-" + variant;
  const nodes: Node[] = [
    { id: "agent", x: 55, y: 330, width: 280, height: 188, title: "Agent", lines: ["Claude Code, Codex or OpenCode"], files: ["prompt", "workspace/"], note: "+ Ethereum skills, in skills mode", icon: Bot, container: true },
    { id: "chain", x: 435, y: 330, width: 260, height: 108, title: "Chain", lines: ["a fresh chain or a copy of mainnet"], icon: Box, container: true },
    { id: "scorer", x: 815, y: 330, width: 250, height: 108, title: "Scorer", lines: ["Forge tests"], icon: ShieldCheck, container: true },
  ];
  const phoneNodes: Node[] = [
    { ...nodes[0], x: 75, y: 625, width: 185, height: 205, lines: ["Claude Code, Codex ", "or OpenCode"], noteLines: ["+ Ethereum skills,", "in skills mode"] },
    { ...nodes[1], x: 75, y: 1085, width: 185, height: 125, lines: ["a fresh chain or a ", "copy of mainnet"] },
    { ...nodes[2], x: 75, y: 1270, width: 185 },
  ];
  const judge = { x: mobile ? 75 : 55, y: mobile ? 920 : 580, width: mobile ? 185 : 280 };
  return <svg className={"diagram run-diagram diagram-" + variant} viewBox={mobile ? "0 0 345 1735" : "0 0 1120 970"} role="img" aria-labelledby={id + "-title " + id + "-desc"}>
    <title id={id + "-title"}>Inside one run</title>
    <desc id={id + "-desc"}>ETH Evals reads the eval folder, picks the agent, model and mode, and builds the task. Inspect runs three separate containers. The agent sends transactions to the chain. The scorer reads the chain state with Forge tests. An LLM judge answers yes-or-no questions about the transcript. ETH Evals records one result per run and publishes results with logs on the website.</desc>
    <Arrows id={id} />
    <rect className="diagram-box evals-frame" x={mobile ? 5 : 10} y="10" width={mobile ? 335 : 1100} height={mobile ? 1705 : 950} rx="12" />
    <text className="diagram-title evals-frame-title" x={mobile ? 25 : 35} y="43">ETH Evals</text>
    <text className="diagram-title run-band-title" x={mobile ? 75 : 55} y="79">Decide what to run</text>
    <RunStep x={mobile ? 75 : 55} y={105} width={mobile ? 185 : 200} title="Eval folder" lines={["prompt, files, checks"]} />
    <RunStep x={mobile ? 75 : 365} y={mobile ? 245 : 105} width={mobile ? 185 : 300} title="Find what hasn't run" lines={["agent, model and mode", "with no result yet"]} />
    <RunStep x={mobile ? 75 : 775} y={mobile ? 385 : 105} width={mobile ? 185 : 290} title="Build the task" lines={mobile ? ["prompt, agent, checks,", "containers"] : ["prompt, agent, checks, containers"]} />
    <Edge d={mobile ? "M167.5 205V242" : "M255 155H362"} id={id} />
    <Edge d={mobile ? "M167.5 345V382" : "M665 155H772"} id={id} />
    <Edge d={mobile ? "M167.5 485V522" : "M920 205V227H560V247"} id={id} />
    {mobile ? <rect className="diagram-box inspect-frame" x="25" y="525" width="295" height="890" rx="10" />
      : <path className="diagram-box inspect-frame" d="M45 250H1075Q1085 250 1085 260V455Q1085 465 1075 465H370Q360 465 360 475V685Q360 695 350 695H45Q35 695 35 685V260Q35 250 45 250Z" />}
    <a href="https://inspect.aisi.org.uk/"><text className="diagram-title inspect-title" x={mobile ? 75 : 560} y={mobile ? 557 : 282} textAnchor={mobile ? undefined : "middle"}>Inspect runs it</text></a>
    <text className="diagram-sub" x={mobile ? 75 : 560} y={mobile ? 581 : 306} textAnchor={mobile ? undefined : "middle"}>{mobile ? <><tspan x="75">starts the containers, </tspan><tspan x="75" dy="18">records the transcript</tspan></> : "starts the containers, records the transcript"}</text>
    {mobile ? <>
      <Edge d="M75 805H50V1139H72" id={id} />
      <text className="edge-label" x="65" y="858">sends transactions</text>
      <Edge d="M225 830V917" id={id} />
      <text className="edge-label" x="231" y="893">transcript</text>
      <Edge d="M167.5 1270V1213" id={id} />
      <text className="edge-label" x="184" y="1235"><tspan x="184">reads the </tspan><tspan x="184" dy="18">chain state</tspan></text>
      <Edge d="M167.5 1028V1050H290V1535H263" id={id} />
      <text className="edge-label" x="185" y="1041">judge output</text>
      <Edge d="M167.5 1378V1497" id={id} />
      <text className="edge-label" x="184" y="1445">checks</text>
    </> : <>
      <Edge d="M335 384H432" id={id} />
      <text className="edge-label" x="385" y="350" textAnchor="middle"><tspan x="385">sends </tspan><tspan x="385" dy="18">transactions</tspan></text>
      <Edge d="M815 384H698" id={id} />
      <text className="edge-label" x="755" y="350" textAnchor="middle"><tspan x="755">reads the </tspan><tspan x="755" dy="18">chain state</tspan></text>
      <Edge d="M195 518V577" id={id} />
      <text className="edge-label" x="211" y="555">transcript</text>
      <Edge d="M195 670V780H337" id={id} />
      <text className="edge-label" x="211" y="717">judge output</text>
      <Edge d="M940 438V780H783" id={id} />
      <text className="edge-label" x="956" y="640">checks</text>
    </>}
    {(mobile ? phoneNodes : nodes).map((node) => <DiagramNode key={node.id} node={node} />)}
    <g className="diagram-node">
      <rect className="diagram-box" x={judge.x} y={judge.y} width={judge.width} height={mobile ? 108 : 90} rx="10" />
      <Scale className="diagram-icon" x={judge.x + 18} y={judge.y + 18} width="24" height="24" strokeWidth="1.6" />
      <text className="diagram-title" x={judge.x + 54} y={judge.y + 35}>LLM as judge</text>
      <text className="diagram-sub" x={judge.x + 18} y={judge.y + 65}>{mobile ? <><tspan x={judge.x + 18}>answers yes-or-no </tspan><tspan x={judge.x + 18} dy="18">questions</tspan></> : "answers yes-or-no questions"}</text>
    </g>
    <text className="diagram-title run-band-title" x={mobile ? 75 : 340} y={mobile ? 1472 : 722}>Record it</text>
    <g className="diagram-node"><rect className="diagram-box" x={mobile ? 75 : 340} y={mobile ? 1500 : 745} width={mobile ? 185 : 440} height="70" rx="10" />
      <text className="diagram-title" x={mobile ? 167.5 : 560} y={mobile ? 1541 : 786} textAnchor="middle">One result per run</text></g>
    <Edge d={mobile ? "M167.5 1570V1617" : "M560 815V857"} id={id} />
    <g className="diagram-node"><rect className="diagram-box" x={mobile ? 75 : 340} y={mobile ? 1620 : 860} width={mobile ? 185 : 440} height={mobile ? 80 : 65} rx="10" />
      <text className="diagram-title" x={mobile ? 167.5 : 560} y={mobile ? 1654 : 898} textAnchor="middle">{mobile ? <><tspan x="167.5">Results + logs </tspan><tspan x="167.5" dy="20">on the website</tspan></> : "Results + logs on the website"}</text></g>
  </svg>;
}

export function RunDiagram() {
  return <><RunLayout /><RunLayout mobile /></>;
}
