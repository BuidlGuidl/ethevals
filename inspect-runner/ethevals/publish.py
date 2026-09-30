"""Plan release assets from the logs referenced by one results file."""

import json
import re
import subprocess
from pathlib import Path


def publish_logs(output: Path, repo: str, run_id: str, commit: str,
                 *, publish: bool = False,
                 rows: list[dict] | None = None, resume: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise ValueError("GitHub repo must have the form owner/name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id):
        raise ValueError("run-id must use 1 to 100 letters, digits, underscores, or hyphens")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("commit must be a full Git commit SHA")
    tag = f"results-{run_id}"
    base = f"https://github.com/{repo}/releases/download"
    root = output.resolve()
    if "#" in str(root):
        raise ValueError("Output path cannot contain #: gh treats it as an asset label separator")
    if rows is None:
        rows = [json.loads(line) for line in (root / "rows.jsonl").read_text().splitlines() if line.strip()]
    published = {
        Path(row["log_file"]).name
        for receipt in (root / "published").glob("results-*.jsonl")
        for line in receipt.read_text().splitlines() if line.strip()
        for row in [json.loads(line)]
    }
    assets = {}
    linked = []
    skipped = {"published": 0}
    for line, row in enumerate(rows, 1):
        if row.get("status") not in {"passed", "failed"}:
            skipped["non_final"] = skipped.get("non_final", 0) + 1
            continue
        relative = Path(row["log_file"])
        if row.get("log_url") or relative.name in published:
            skipped["published"] += 1
            continue
        if relative.is_absolute() or relative.parts[:1] != ("logs",) or ".." in relative.parts:
            raise ValueError(f"row {line}: log_file must be a relative path under logs/")
        source = root / relative
        if "#" in str(source):
            raise ValueError(f"row {line}: log path cannot contain #")
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
        linked.append({**row, "log_url": asset["url"]})
    if len(assets) > 1000:
        raise ValueError("A release accepts at most 1000 assets; split the results run")
    command = ["gh", "release", "create", tag, "--repo", repo, "--target", commit,
               "--latest=false", "--title", f"Results {run_id}", "--notes",
               "Full Inspect logs for this results run. Download a .eval file and open its directory with inspect view.",
               *[asset["source"] for asset in sorted(assets.values(), key=lambda asset: asset["name"])]]
    destination = root / "published" / f"{tag}.jsonl"
    plan = {"dry_run": not publish, "release": tag, "repo": repo, "commit": commit,
            "log_base": base, "rows_file": str(destination), "command": command if assets else [],
            "skipped": skipped,
            "assets": sorted(assets.values(), key=lambda asset: asset["name"])}
    if publish and assets:
        if destination.exists():
            raise ValueError(f"{destination}: release rows already exist; choose a new run-id")
        if resume and subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
            subprocess.run(["gh", "release", "upload", tag, "--repo", repo, "--clobber",
                            *[asset["source"] for asset in plan["assets"]]], check=True, stdout=subprocess.PIPE, text=True)
        else:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in linked))
        temporary.replace(destination)
    return plan
