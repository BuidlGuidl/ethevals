"""Give the judge the project's source, without dependencies or build output."""
from pathlib import Path
import sys

EXCLUDED = {"node_modules", "dist", ".git", ".next", ".vite", "coverage", "build", "out", "cache"}
EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".html", ".sol"}


def snapshot(project: Path) -> str:
    sections = []
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project)
        if EXCLUDED.intersection(relative.parts) or path.is_symlink() or not path.is_file():
            continue
        if path.suffix not in EXTENSIONS and path.name != "package.json":
            continue
        with path.open("r", errors="replace") as source:
            text = source.read(200_000)
        sections.append(f"--- {relative.as_posix()} ---\n{text}\n")
    return "\n".join(sections) or "No project source files were found.\n"


if __name__ == "__main__":
    Path(sys.argv[2]).write_text(snapshot(Path(sys.argv[1])))
