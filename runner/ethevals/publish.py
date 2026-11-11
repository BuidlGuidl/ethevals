"""Stage Harbor trajectories and verifier output for a results release."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time

from .trial_rows import read_rows, trial_identity, write_rows
from .secret_check import require_checked


UPLOAD_BATCH_SIZE = 10
UPLOAD_PAUSE = 20
UPLOAD_TRIES = 7
RATE_LIMIT_WAIT = 60


def _release_files(repo: str, tag: str) -> dict[str, int]:
    release = subprocess.run(["gh", "release", "view", tag, "--repo", repo, "--json", "databaseId"],
                             check=True, capture_output=True, text=True)
    release_id = json.loads(release.stdout)["databaseId"]
    assets = subprocess.run(["gh", "api", f"repos/{repo}/releases/{release_id}/assets?per_page=100",
                             "--paginate", "--slurp"], check=True, capture_output=True, text=True)
    return {asset["name"]: asset["size"] for page in json.loads(assets.stdout) for asset in page}


def publish_logs(output: Path, repo: str, run_id: str, commit: str,
                 *, publish: bool = False, rows: list[dict] | None = None) -> dict:
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
        if row.get("error_kind") in {"secret", "publication"}:
            linked.append(row)
            continue
        hub_url = (row.get("trajectory_url") or "").startswith("https://hub.harborframework.com/jobs/")
        if row.get("verifier_url") and (row.get("trajectory_url") or "").startswith("https://"):
            linked.append(row)
            continue
        checked_job = Path(row["verifier_files"]).parent.parent
        require_checked(checked_job)
        key = hashlib.sha256(json.dumps([trial_identity(row), row.get("checks_generation", 0), row["retry"], row["completed_at"]]).encode()).hexdigest()[:24]
        asset_dir = root / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        links = {}
        if row.get("trajectory_file") and (not row.get("regraded_at") or not row.get("trajectory_download_url")):
            source = Path(row["trajectory_file"])
            if not source.resolve().is_relative_to(checked_job.resolve()):
                raise ValueError("The trajectory must stay inside its checked job")
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Missing trajectory file: {source}")
            name = f"trajectory-{key}.json"
            destination = asset_dir / name
            if source.resolve() != destination:
                shutil.copyfile(source, destination)
            links.update(trajectory_file=str(destination), trajectory_url=row["trajectory_url"] if hub_url else f"{base}/{name}",
                         trajectory_download_url=f"{base}/{name}")
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
        trial = verifier.parent
        if ((trial / "artifacts/workspace").is_dir() and (trial / "artifacts/manifest.json").is_file()
                and not row.get("artifacts_url")):
            artifact_name = f"artifacts-{key}.tar.gz"
            artifact_path = asset_dir / artifact_name
            with tarfile.open(artifact_path, "w:gz") as archive:
                for relative in ("result.json", "lock.json", "agent", "artifacts"):
                    source = trial / relative
                    if source.exists():
                        archive.add(source, arcname=relative)
            assets.append({"name": artifact_name, "source": str(artifact_path), "url": f"{base}/{artifact_name}"})
            links["artifacts_url"] = f"{base}/{artifact_name}"
        linked.append({**row, **links, "verifier_url": f"{base}/{name}"})
    assets = sorted({asset["name"]: asset for asset in assets}.values(), key=lambda asset: asset["name"])
    if len(assets) > 1000:
        raise ValueError("A release accepts at most 1000 assets; split the results job")
    for asset in assets:
        if Path(asset["source"]).stat().st_size >= 2 * 1024**3:
            raise ValueError(f"Release asset must be smaller than 2 GiB: {asset['name']}")
    command = ["gh", "release", "create", tag, "--repo", repo, "--target", commit,
               "--latest=false", "--title", f"Results {run_id}", "--notes",
               "Harbor trajectories and verifier output for these trials."]
    receipt = root / "published" / f"{tag}.jsonl"
    report = {"dry_run": not publish, "release": tag, "repo": repo, "commit": commit,
              "rows_file": str(receipt), "command": command if assets else [],
              "assets": assets, "rows": linked}
    if publish and assets:
        try:
            existing = _release_files(repo, tag)
        except subprocess.CalledProcessError as error:
            if "release not found" not in (error.stderr or "").lower():
                raise
            subprocess.run(command, check=True, capture_output=True, text=True)
            existing = _release_files(repo, tag)
        sizes = {asset["name"]: Path(asset["source"]).stat().st_size for asset in assets}
        pending = [asset for asset in assets if existing.get(asset["name"]) != sizes[asset["name"]]]
        for offset in range(0, len(pending), UPLOAD_BATCH_SIZE):
            if offset:
                time.sleep(UPLOAD_PAUSE)
            batch = pending[offset:offset + UPLOAD_BATCH_SIZE]
            for attempt in range(UPLOAD_TRIES):
                missing = [asset for asset in batch if existing.get(asset["name"]) != sizes[asset["name"]]]
                if not missing:
                    break
                try:
                    subprocess.run(["gh", "release", "upload", tag, "--repo", repo, "--clobber",
                                    *[asset["source"] for asset in missing]],
                                   check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as error:
                    message = (error.stderr or "").lower()
                    if not any(marker in message for marker in ("rate limit", "http 429", "too many requests")):
                        raise
                    existing = _release_files(repo, tag)
                    if all(existing.get(asset["name"]) == sizes[asset["name"]] for asset in batch):
                        break
                    if attempt == UPLOAD_TRIES - 1:
                        uploaded = sum(existing.get(name) == size for name, size in sizes.items())
                        raise RuntimeError(f"Release {tag}: {uploaded} files up, {len(assets) - uploaded} left. "
                                           "Rerun the failed job to continue the upload.") from error
                    time.sleep(RATE_LIMIT_WAIT * 2**attempt)
                else:
                    existing.update((asset["name"], sizes[asset["name"]]) for asset in missing)
                    break
        write_rows(receipt, linked)
    return report
