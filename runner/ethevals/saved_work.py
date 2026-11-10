"""Fetch published work without model credentials."""
import json
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from threading import Lock
from urllib.request import urlopen

from .checks import read_details
from .task_hashes import digest

_downloads = Lock()


def asset(url: str, cache: Path) -> Path:
    target = cache / (digest(url).removeprefix("sha256:") + (".json" if url.endswith(".json") else ".tar.gz"))
    if not target.exists():
        cache.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=45) as response:
            data = response.read()
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
    return target


def unpack(source: Path, destination: Path) -> Path:
    if not destination.exists():
        destination.mkdir(parents=True)
        try:
            with tarfile.open(source) as archive:
                archive.extractall(destination, filter="data")
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination


def trajectory_url(row: dict) -> str | None:
    url = row.get("trajectory_download_url") or row.get("trajectory_url") or ""
    if url.startswith("https://hub.harborframework.com/"):
        verifier = row.get("verifier_url") or ""
        return verifier.replace("/verifier-", "/trajectory-").replace(".tar.gz", ".json") if "/verifier-" in verifier else None
    return url if url.startswith(("https://", "http://")) else None


def ci_trial(row: dict, cache: Path) -> Path:
    """Recover older contract trials from the CI artifact while it exists."""
    match = re.fullmatch(r"https://github.com/([^/]+/[^/]+)/releases/download/results-([0-9]+)/.*", row.get("verifier_url") or "")
    if not match:
        raise ValueError("No saved contract files are published")
    repo, run_id = match.groups()
    root = cache / f"ci-{run_id}"
    # Rows from one run share its plan and artifact cache.
    with _downloads:
        plan = root / "plan"
        if not list(plan.rglob("trials.json")):
            subprocess.run(["gh", "run", "download", run_id, "--repo", repo, "--pattern", f"trial-plan-{run_id}-*",
                            "--dir", str(plan)], check=True, capture_output=True)
        files = list(plan.rglob("trials.json"))
        if not files:
            raise ValueError("The saved CI plan is unavailable")
        indices = [index for index, batch in enumerate(json.loads(files[0].read_text()))
                   if any(all(item.get(key) == row.get(key) for key in (
                       "task_id", "task_hash", "agent", "model", "effort", "mode", "trial", "retry"))
                          for item in batch["missing"])]
        for index in indices:
            folder = root / str(index)
            if not folder.exists():
                subprocess.run(["gh", "run", "download", run_id, "--repo", repo,
                                "--pattern", f"trial-run-{run_id}-*-{index}", "--dir", str(folder)],
                               check=True, capture_output=True)
            for board in folder.rglob("board.json"):
                metadata = json.loads(board.read_text())
                if all(metadata.get(key) == row.get(key) for key in (
                        "task_id", "task_hash", "agent", "model", "effort", "mode", "trial", "retry")):
                    for result in board.parent.glob("*/result.json"):
                        record = json.loads(result.read_text())
                        url = row.get("trajectory_url") or ""
                        source_id = url.rsplit("/trials/", 1)[-1].rstrip("/") if url.startswith("https://hub.harborframework.com/jobs/") else None
                        if source_id and str(record["id"]) != source_id:
                            continue
                        if row.get("completed_at") and (not record.get("finished_at") or
                                datetime.fromisoformat(record["finished_at"]) != datetime.fromisoformat(row["completed_at"])):
                            continue
                        if (result.parent / "artifacts/manifest.json").is_file():
                            return result.parent
    raise ValueError("The saved contract files are unavailable")


def fetch_work(row: dict, kind: str, cache: Path) -> dict:
    key = digest([row.get("trajectory_url"), row.get("verifier_url"), row.get("task_hash"),
                  row.get("model"), row.get("mode"), row.get("trial"), row.get("retry")]).removeprefix("sha256:")
    directory = cache / key
    directory.mkdir(parents=True, exist_ok=True)
    if kind == "contract":
        local = Path(row["verifier_files"]).parent if row.get("verifier_files") else None
        if local and (local / "artifacts/manifest.json").is_file():
            target = directory / "trial"
            if not target.exists():
                shutil.copytree(local, target)
            return {"trial": str(target.resolve())}
        if row.get("artifacts_url"):
            return {"trial": str(unpack(asset(row["artifacts_url"], cache), directory / "trial").resolve())}
        return {"trial": str(ci_trial(row, cache).resolve())}
    local = Path(row["trajectory_file"]) if row.get("trajectory_file") else None
    if not local or not local.is_file():
        url = trajectory_url(row)
        if not url:
            raise ValueError("The saved trajectory is unavailable")
        local = asset(url, cache)
    json.loads(local.read_text())["steps"]
    target = directory / "trajectory.json"
    if local.resolve() != target.resolve():
        shutil.copyfile(local, target)
    work = {"trajectory": str(target.resolve())}
    if kind == "judge" or row.get("judge"):
        verifier = Path(row["verifier_files"]) if row.get("verifier_files") else None
        if not verifier or not verifier.is_dir():
            if not row.get("verifier_url"):
                raise ValueError("The saved judge input is unavailable")
            verifier = unpack(asset(row["verifier_url"], cache), directory / "verifier")
        read_details(verifier)
        target = directory / "verifier"
        if verifier.resolve() != target.resolve():
            shutil.copytree(verifier, target, dirs_exist_ok=True)
        work["verifier"] = str(target.resolve())
    return work
