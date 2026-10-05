const rows = [
  "███████╗████████╗██╗  ██╗███████╗██╗   ██╗ █████╗ ██╗     ███████╗",
  "██╔════╝╚══██╔══╝██║  ██║██╔════╝██║   ██║██╔══██╗██║     ██╔════╝",
  "█████╗     ██║   ███████║█████╗  ██║   ██║███████║██║     ███████╗",
  "██╔══╝     ██║   ██╔══██║██╔══╝  ╚██╗ ██╔╝██╔══██║██║     ╚════██║",
  "███████╗   ██║   ██║  ██║███████╗ ╚████╔╝ ██║  ██║███████╗███████║",
  "╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚══════╝",
];

const width = 10, height = 19, cx = 5, cy = 9.5, gap = 2.1;
const lines: Record<string, number[][][]> = {
  "═": [[[0, cy-gap], [width, cy-gap]], [[0, cy+gap], [width, cy+gap]]],
  "║": [[[cx-gap, 0], [cx-gap, height]], [[cx+gap, 0], [cx+gap, height]]],
  "╗": [[[0, cy-gap], [cx+gap, cy-gap], [cx+gap, height]], [[0, cy+gap], [cx-gap, cy+gap], [cx-gap, height]]],
  "╔": [[[width, cy-gap], [cx-gap, cy-gap], [cx-gap, height]], [[width, cy+gap], [cx+gap, cy+gap], [cx+gap, height]]],
  "╝": [[[0, cy+gap], [cx+gap, cy+gap], [cx+gap, 0]], [[0, cy-gap], [cx-gap, cy-gap], [cx-gap, 0]]],
  "╚": [[[width, cy+gap], [cx-gap, cy+gap], [cx-gap, 0]], [[width, cy-gap], [cx+gap, cy-gap], [cx+gap, 0]]],
};

export function Logo({ id }: { id: string }) {
  return <svg viewBox={`0 0 ${rows[0].length * width} ${rows.length * height}`} aria-hidden="true">
    <defs><linearGradient id={id} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2={rows[0].length * width} y2="0"><stop offset="0" stopColor="#8c8dfc" /><stop offset=".55" stopColor="#627eea" /><stop offset="1" stopColor="#62d3e5" /></linearGradient></defs>
    <g fill={`url(#${id})`}>{rows.flatMap((row, y) => [...row].map((char, x) => char === "█"
      ? <rect key={`${x}-${y}`} x={x * width} y={y * height} width={width} height={height} /> : null))}</g>
    <path fill="none" stroke={`url(#${id})`} strokeWidth="1.1" d={rows.flatMap((row, y) => [...row].flatMap((char, x) =>
      (lines[char] ?? []).map((line) => `M${line.map(([px, py]) => `${x * width + px} ${y * height + py}`).join("L")}`))).join("")} />
  </svg>;
}
