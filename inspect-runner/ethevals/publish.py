"""Plan release assets from the logs referenced by one results file."""

import json
import re
import subprocess
from pathlib import Path


def publish_logs(output: Path, repo: str, run_id: str, target: str,
                 *, publish: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise ValueError("GitHub repo must have the form owner/name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id):
        raise ValueError("run-id must use 1 to 100 letters, digits, underscores, or hyphens")
    if not re.fullmatch(r"[0-9a-f]{40}", target):
        raise ValueError("target must be a full Git commit SHA")
    tag = f"results-{run_id}"
    base = f"https://github.com/{repo}/releases/download"
    root = output.resolve()
    rows = [json.loads(line) for line in (root / "rows.jsonl").read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError("No results rows to publish")
    assets = {}
    linked = []
    for line, row in enumerate(rows, 1):
        relative = Path(row["log_file"])
        if relative.is_absolute() or relative.parts[:1] != ("logs",) or ".." in relative.parts:
            raise ValueError(f"row {line}: log_file must be a relative path under logs/")
        source = root / relative
        if not source.resolve().is_relative_to(root / "logs") or source.is_symlink():
            raise ValueError(f"row {line}: log_file must stay under logs/")
        name = source.name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.eval", name):
            raise ValueError(f"row {line}: unsafe release asset name {name!r}")
        if not source.is_file() or source.stat().st_size >= 2 * 1024**3:
            raise ValueError(f"row {line}: log must exist and be smaller than 2 GiB: {source}")
        if name in assets and assets[name]["source"] != str(source):
            raise ValueError(f"row {line}: duplicate release asset name {name}")
        asset = assets.setdefault(name, {"name": name, "source": str(source),
                                        "url": f"{base}/{tag}/{name}", "rows": []})
        asset["rows"].append({"line": line, **{key: row[key] for key in ("eval_id", "model", "mode", "epoch")}})
        linked.append({**row, "log_file": f"{tag}/{name}"})
    if len(assets) > 1000:
        raise ValueError("A release accepts at most 1000 assets; split the results run")
    command = ["gh", "release", "create", tag, "--repo", repo, "--target", target,
               "--latest=false", "--title", f"Results {run_id}", "--notes",
               "Full Inspect logs for this results run. Download a .eval file and open its directory with inspect view.",
               *[asset["source"] for asset in sorted(assets.values(), key=lambda asset: asset["name"])]]
    destination = root / "published" / "rows.jsonl"
    plan = {"dry_run": not publish, "release": tag, "repo": repo, "target": target,
            "log_base": base, "rows_file": str(destination), "command": command,
            "assets": sorted(assets.values(), key=lambda asset: asset["name"])}
    # A dry run stages local rows too. CI installs these only after publication succeeds.
    if publish:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in linked))
    temporary.replace(destination)
    return plan
