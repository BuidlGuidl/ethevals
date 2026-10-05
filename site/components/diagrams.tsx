import { FileText, Cpu, ShieldCheck, GitMerge, Terminal, GitPullRequest, Table2, Database, Bot, Box, Scale, type LucideIcon } from "lucide-react";

type Node = { id: string; x: number; y: number; width?: number; height?: number; title: string; titleLines?: string[]; lines: string[]; icon: LucideIcon; kind?: "auto" | "dest"; container?: boolean; files?: string[]; note?: string };
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
    {node.note && <text className="diagram-sub diagram-dim" x={node.x + 18} y={node.y + 171}>{node.note}</text>}
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
    ...[60, 200, 390, 540, 926, 1070, 1214].map((y, index) => ({ ...nodes[index], x: 35, y, width: 260 })),
    { ...nodes[7], x: 35, y: 710, width: 260, height: 108, titleLines: undefined },
  ];
  const phoneEdges = [
    ["phase", "M35 114H10V335"], ["phase", "M165 308V335H10"], ["phase", "M10 335V444H32"],
    ["phase", "M165 498V537"], ["auto", "M165 648V678H10V980H32"],
    ["auto", "M165 678V707"], ["auto", "M165 1034V1067"], ["auto", "M165 1178V1211"],
  ];
  return <svg className={`diagram pipeline-diagram diagram-${variant}`} viewBox={mobile ? "0 0 330 1350" : "0 0 1320 400"} role="img" aria-labelledby={`${id}-title ${id}-desc`}>
    <title id={`${id}-title`}>From pull request to website</title><desc id={`${id}-desc`}>Eval and model pull requests pass validity checks with a mock model and maintainer review. After merge, CI runs new epochs for every agent and model. A results pull request updates the website. Model-only evals also go to Hugging Face.</desc>
    <Arrows id={id} />
    {[["1 · Contribute", 20, 200], ["2 · Review", 240, 640], ["3 · Automatic on main", 680, 1300]].map(([label, start, end], index) => <g key={label} className={`diagram-zone ${index === 2 ? "auto" : "phase"}`}><path d={mobile ? `M35 ${[34, 362, 898][index]}H295` : `M${start} 34H${end}`} /><text x={mobile ? 35 : start} y={mobile ? [22, 350, 886][index] : 22}>{label}</text></g>)}
    {(mobile ? phoneEdges : edges).map(([kind, d], index) => <Edge key={index} d={d} kind={kind} id={id} index={index} arrow={!mobile || index > 1} />)}
    {(mobile ? phoneNodes : nodes).map((node) => <DiagramNode key={node.id} node={node} />)}
  </svg>;
}

export function PipelineDiagram() {
  return <><PipelineLayout /><PipelineLayout mobile /></>;
}

function EvalsBox({ x, y, width, lines }: { x: number; y: number; width: number; lines: string[] }) {
  return <g className="diagram-node"><rect className="diagram-box" x={x} y={y} width={width} height={lines.length > 1 ? 110 : 100} rx="10" />
    <text className="diagram-title" x={x + width / 2} y={y + 34} textAnchor="middle">ETH Evals</text>
    <text className="diagram-sub" x={x + width / 2} y={y + 62} textAnchor="middle">{lines.map((line, i) => <tspan key={line} x={x + width / 2} dy={i ? 20 : 0}>{line}{i < lines.length - 1 ? " " : ""}</tspan>)}</text>
  </g>;
}

function RunLayout({ mobile = false }: { mobile?: boolean }) {
  const variant = mobile ? "phone" : "desktop", id = `run-${variant}`;
  const nodes: Node[] = [
    { id: "agent", x: 40, y: 300, width: 280, height: 188, title: "Agent", lines: ["Claude Code, Codex or OpenCode"], files: ["prompt", "workspace/"], note: "+ Ethereum skills, in skills mode", icon: Bot, container: true },
    { id: "chain", x: 430, y: 300, width: 260, height: 108, title: "Chain", lines: ["a fresh chain or a copy of mainnet"], icon: Box, container: true },
    { id: "scorer", x: 820, y: 300, width: 260, height: 108, title: "Scorer", lines: ["checks the result"], icon: ShieldCheck, container: true },
  ];
  const judge = { x: mobile ? 45 : 40, y: mobile ? 585 : 550, width: mobile ? 230 : 280 };
  const phoneNodes = nodes.map((node, index) => ({ ...node, x: 45, y: [340, 745, 955][index], width: 230,
    height: [188, 125, 108][index], lines: index === 1 ? ["a fresh chain or a", "copy of mainnet"] : node.lines }));
  return <svg className={`diagram run-diagram diagram-${variant}`} viewBox={mobile ? "0 0 320 1290" : "0 0 1120 820"} role="img" aria-labelledby={`${id}-title ${id}-desc`}>
    <title id={`${id}-title`}>Inside one run</title><desc id={`${id}-desc`}>ETH Evals reads the eval folder and picks the agent, model and mode. Inspect starts three separate containers and records the transcript. The agent sends transactions to the chain. The scorer reads the chain state. An LLM judge answers yes-or-no questions about the transcript. ETH Evals combines the checks into Results + logs on the website.</desc>
    <Arrows id={id} />
    <EvalsBox x={mobile ? 45 : 310} y={20} width={mobile ? 230 : 500} lines={mobile ? ["reads the eval folder,", "picks agent, model and mode"] : ["reads the eval folder, picks agent, model and mode"]} />
    <Edge d={mobile ? "M160 130V237" : "M560 120V217"} id={id} />
    <text className="edge-label" x={mobile ? 176 : 576} y={mobile ? 204 : 174}>hands the task to</text>
    <rect className="diagram-box inspect-frame" x={mobile ? 5 : 20} y={mobile ? 240 : 220} width={mobile ? 310 : 1080} height={mobile ? 855 : 440} rx="10" />
    <a href="https://inspect.aisi.org.uk/"><text className="diagram-title inspect-title" x={mobile ? 45 : 40} y={mobile ? 270 : 250}>Inspect</text></a>
    <text className="diagram-sub" x={mobile ? 45 : 40} y={mobile ? 294 : 274}>{mobile ? <><tspan x="45">starts the containers, </tspan><tspan x="45" dy="18">records the transcript</tspan></> : "starts the containers, records the transcript"}</text>
    {mobile ? <>
      <Edge d="M160 528V582" id={id} /><text className="edge-label" x="176" y="559">transcript</text>
      <Edge d="M45 434H25V799H42" id={id} /><text className="edge-label" x="45" y="704"><tspan x="45">sends </tspan><tspan x="45" dy="16">transactions</tspan></text>
      <Edge d="M160 955V873" id={id} /><text className="edge-label" x="176" y="909"><tspan x="176">reads the </tspan><tspan x="176" dy="16">chain state</tspan></text>
      <Edge d="M275 630H295V1202H278" id={id} />
      <Edge d="M160 1063V1137" id={id} /><text className="edge-label" x="176" y="1107">checks</text>
    </> : <>
      <Edge d="M320 354H427" id={id} /><text className="edge-label" x="375" y="320" textAnchor="middle"><tspan x="375">sends </tspan><tspan x="375" dy="18">transactions</tspan></text>
      <Edge d="M820 354H693" id={id} /><text className="edge-label" x="755" y="320" textAnchor="middle"><tspan x="755">reads the </tspan><tspan x="755" dy="18">chain state</tspan></text>
      <Edge d="M180 488V547" id={id} /><text className="edge-label" x="196" y="525">transcript</text>
      <Edge d="M950 408V750H813" id={id} /><text className="edge-label" x="966" y="600">checks</text>
      <Edge d="M180 640V750H307" id={id} />
    </>}
    {(mobile ? phoneNodes : nodes).map((node) => <DiagramNode key={node.id} node={node} />)}
    <g className="diagram-node"><rect className="diagram-box" x={judge.x} y={judge.y} width={judge.width} height="90" rx="10" />
      <Scale className="diagram-icon" x={judge.x + 18} y={judge.y + 18} width="24" height="24" strokeWidth="1.6" />
      <text className="diagram-title" x={judge.x + 54} y={judge.y + 35}>LLM as judge</text>
      <text className="diagram-sub" x={judge.x + 18} y={judge.y + 65}>answers yes-or-no questions</text>
    </g>
    <EvalsBox x={mobile ? 45 : 310} y={mobile ? 1140 : 700} width={mobile ? 230 : 500} lines={mobile ? ["turns the log into Results + logs", "on the website"] : ["turns the log into Results + logs on the website"]} />
  </svg>;
}

export function RunDiagram() {
  return <><RunLayout /><RunLayout mobile /></>;
}
