"""Stage Harbor trajectories and verifier output for a results release."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

from .trial_rows import read_rows, trial_identity, write_rows


def publish_logs(output: Path, repo: str, run_id: str, commit: str,
                 *, publish: bool = False, rows: list[dict] | None = None,
                 resume: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise ValueError("GitHub repo must have the form owner/name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id):
        raise ValueError("run-id must use 1 to 100 letters, digits, underscores, or hyphens")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("commit must be a full Git commit SHA")
    root = output.resolve()
    if "#" in str(root):
        raise ValueError("Output path cannot contain #: gh treats it as an asset label separator")
    tag = f"results-{run_id}"
    base = f"https://github.com/{repo}/releases/download/{tag}"
    assets, linked = [], []
    for row in rows if rows is not None else read_rows(root / "rows.jsonl"):
        if (row.get("trajectory_url") or "").startswith("https://"):
            linked.append(row)
            continue
        key = hashlib.sha256(json.dumps([trial_identity(row), row["attempt"], row["completed_at"]]).encode()).hexdigest()[:24]
        asset_dir = root / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        links = {}
        if row.get("trajectory_file"):
            source = Path(row["trajectory_file"])
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Missing trajectory file: {source}")
            name = f"trajectory-{key}.json"
            destination = asset_dir / name
            if source.resolve() != destination:
                shutil.copyfile(source, destination)
            links.update(trajectory_file=str(destination), trajectory_url=f"{base}/{name}")
            assets.append({"name": name, "source": str(destination), "url": f"{base}/{name}"})
        verifier = Path(row["verifier_files"])
        if not verifier.is_dir() or verifier.is_symlink():
            raise ValueError(f"Missing verifier output: {verifier}")
        name = f"verifier-{key}.tar.gz"
        destination = asset_dir / name
        with tarfile.open(destination, "w:gz") as archive:
            for source in sorted(verifier.rglob("*")):
                if source.is_symlink() or not source.resolve().is_relative_to(verifier.resolve()):
                    raise ValueError(f"Verifier output must stay inside its directory: {source}")
                if source.is_file():
                    archive.add(source, arcname=source.relative_to(verifier), recursive=False)
        assets.append({"name": name, "source": str(destination), "url": f"{base}/{name}"})
        linked.append({**row, **links, "verifier_url": f"{base}/{name}"})
    assets = sorted({asset["name"]: asset for asset in assets}.values(), key=lambda asset: asset["name"])
    if len(assets) > 1000:
        raise ValueError("A release accepts at most 1000 assets; split the results job")
    for asset in assets:
        if Path(asset["source"]).stat().st_size >= 2 * 1024**3:
            raise ValueError(f"Release asset must be smaller than 2 GiB: {asset['name']}")
    command = ["gh", "release", "create", tag, "--repo", repo, "--target", commit,
               "--latest=false", "--title", f"Results {run_id}", "--notes",
               "Harbor trajectories and verifier output for these trials.",
               *[asset["source"] for asset in assets]]
    receipt = root / "published" / f"{tag}.jsonl"
    report = {"dry_run": not publish, "release": tag, "repo": repo, "commit": commit,
              "rows_file": str(receipt), "command": command if assets else [],
              "assets": assets, "rows": linked}
    if publish and assets:
        if resume and subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
            command = ["gh", "release", "upload", tag, "--repo", repo, "--clobber",
                       *[asset["source"] for asset in assets]]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
        write_rows(receipt, linked)
    return report
