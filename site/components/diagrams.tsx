import { FileText, Cpu, ShieldCheck, GitMerge, Terminal, GitPullRequest, Table2, Database, Bot, Box, Scale, FileCheck, type LucideIcon } from "lucide-react";

type Node = { id: string; x: number; y: number; width?: number; height?: number; title: string; lines: string[]; icon: LucideIcon; kind?: "auto" | "dest" };
function DiagramNode({ node }: { node: Node }) {
  const Icon = node.icon;
  return <g className={`diagram-node ${node.kind ?? "phase"}`}>
    <rect className="diagram-box" x={node.x} y={node.y} width={node.width ?? 180} height={node.height ?? 108} rx="10" />
    <Icon className="diagram-icon" x={node.x + 16} y={node.y + 15} width={24} height={24} strokeWidth={1.6} />
    <text className="diagram-title" x={node.x + 18} y={node.y + 62}>{node.title}</text>
    {node.lines.map((line, i) => <text key={i} className="diagram-sub" x={node.x + 18} y={node.y + 84 + i * 17}>{line}</text>)}
  </g>;
}
function Arrows({ id }: { id: string }) {
  return <defs>{["phase", "auto"].map((kind) => <marker key={kind} id={`${id}-${kind}`} className={`diagram-marker ${kind}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M1.5 1.5 8.5 5 1.5 8.5" /></marker>)}</defs>;
}
function Edge({ d, kind = "auto", id, index = 0 }: { d: string; kind?: string; id: string; index?: number }) {
  return <g className={`diagram-edge ${kind}`}><path d={d} markerEnd={`url(#${id}-${kind})`} />
    <path className="diagram-pulse" d={d} pathLength="100" style={{ animationDelay: `${index * .45}s` }} /></g>;
}
function elbow(x1: number, y1: number, middle: number, y2: number, x2: number) {
  const r = 8, dir = y2 > y1 ? 1 : -1;
  return `M${x1} ${y1}H${middle-r}Q${middle} ${y1} ${middle} ${y1+dir*r}V${y2-dir*r}Q${middle} ${y2} ${middle+r} ${y2}H${x2}`;
}

export function PipelineDiagram() {
  const nodes: Node[] = [
    { id: "eval", x: 20, y: 84, title: "Add or edit an eval", lines: ["a folder: prompt, files, scoring"], icon: FileText },
    { id: "model", x: 20, y: 246, title: "Add a model", lines: ["one entry in config.yaml"], icon: Cpu },
    { id: "checks", x: 240, y: 165, title: "PR: validity checks", lines: ["no API keys spent"], icon: ShieldCheck },
    { id: "merge", x: 460, y: 165, title: "Merge to main", lines: ["a maintainer reviews"], icon: GitMerge },
    { id: "ci", x: 680, y: 66, title: "CI runs only what's new", lines: ["within a budget"], icon: Terminal, kind: "auto" },
    { id: "pr", x: 900, y: 66, title: "Results PR", lines: ["rows + Inspect logs"], icon: GitPullRequest, kind: "auto" },
    { id: "website", x: 1120, y: 66, title: "Merge → website", lines: ["the board updates"], icon: Table2, kind: "dest" },
    { id: "hf", x: 680, y: 264, title: "Publish HF dataset", lines: ["model-only evals"], icon: Database, kind: "auto" },
  ];
  const edges = [
    ["phase", elbow(200, 138, 220, 219, 237)], ["phase", elbow(200, 300, 220, 219, 237)], ["phase", "M420 219H457"],
    ["auto", elbow(640, 219, 660, 120, 677)], ["auto", elbow(640, 219, 660, 318, 677)],
    ["auto", "M860 120H897"], ["auto", "M1080 120H1117"],
  ];
  return <svg className="diagram pipeline-diagram" viewBox="0 0 1320 400" role="img" aria-labelledby="pipeline-title pipeline-desc">
    <title id="pipeline-title">From pull request to website</title><desc id="pipeline-desc">Eval and model pull requests pass validity checks and maintainer review. After merge, CI runs new epochs within a budget. A results pull request updates the website. Model-only evals also go to Hugging Face.</desc>
    <Arrows id="pipeline-arrow" />
    {[["1 · Contribute", 20, 200], ["2 · Review", 240, 640], ["3 · Automatic on main", 680, 1300]].map(([label, start, end], index) => <g key={label} className={`diagram-zone ${index === 2 ? "auto" : "phase"}`}><path d={`M${start} 34H${end}`} /><text x={start} y="22">{label}</text></g>)}
    {edges.map(([kind, d], index) => <Edge key={index} d={d} kind={kind} id="pipeline-arrow" index={index} />)}
    {nodes.map((node) => <DiagramNode key={node.id} node={node} />)}
  </svg>;
}

export function RunDiagram() {
  const nodes: Node[] = [
    { id: "agent", x: 50, y: 220, width: 350, height: 125, title: "Claude Code · Codex CLI · OpenCode", lines: [], icon: Bot },
    { id: "chain", x: 480, y: 90, width: 230, height: 125, title: "Private chain", lines: ["Anvil: a fresh chain", "or a mainnet fork"], icon: Box, kind: "auto" },
    { id: "scorer", x: 780, y: 90, width: 230, height: 125, title: "Scorer", lines: ["Forge tests + setup"], icon: ShieldCheck },
    { id: "grader", x: 780, y: 290, width: 230, height: 140, title: "Grader model", lines: ["reads the transcript,", "answers yes-or-no questions"], icon: Scale },
    { id: "result", x: 1090, y: 290, width: 220, height: 140, title: "Result row + Inspect log", lines: [], icon: FileCheck, kind: "dest" },
  ];
  return <svg className="diagram run-diagram" viewBox="0 0 1340 470" role="img" aria-labelledby="run-title run-desc">
    <title id="run-title">Inside one run</title><desc id="run-desc">The agent works in a sandbox and reaches a private chain through filtered RPC. It has no route to the scorer. The scorer checks the chain after the agent stops. A grader reads the transcript. The result row and Inspect log record the run.</desc>
    <Arrows id="run-arrow" />
    <rect className="sandbox-box" x="20" y="35" width="410" height="360" rx="10" />
    <text className="sandbox-title" x="40" y="65">Agent sandbox</text>
    <text className="diagram-input" x="50" y="115">prompt</text><text className="diagram-input" x="50" y="150">workspace/ + chain.json</text>
    <text className="diagram-input" x="50" y="185">skills pack (Internet + Skills only)</text>
    <Edge d={elbow(400, 282, 455, 152, 477)} id="run-arrow" /><text className="edge-label" x="445" y="250">filtered RPC</text>
    <Edge d="M710 152H777" id="run-arrow" kind="phase" />
    <path className="no-route" d="M430 370H742V240H815V215" /><path className="no-route-cross" d="m557 362 16 16m0-16-16 16" />
    <text className="edge-label blocked" x="592" y="357">no route</text>
    <Edge d="M895 215V287" id="run-arrow" kind="phase" /><Edge d="M1010 360H1087" id="run-arrow" />
    {nodes.map((node) => <DiagramNode key={node.id} node={node} />)}
  </svg>;
}
