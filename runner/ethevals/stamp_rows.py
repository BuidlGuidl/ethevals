"""Stamp saved rows from task folders with matching Harbor digests."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from harbor.publisher.packager import Packager

from .task_hashes import digest, task_hashes


def stamp_rows(rows: list[dict], root: Path) -> list[dict]:
    cache = {}
    stamped = []
    for row in rows:
        if row.get("schema_version") != 8:
            stamped.append(row)
            continue
        key = (row["task_id"], row["task_hash"])
        if key not in cache:
            relative = Path("tasks") / row["task_id"]
            current = root / relative
            if current.is_dir() and "sha256:" + Packager.compute_content_hash(current)[0] == row["task_hash"]:
                cache[key] = task_hashes(current)
            else:
                commits = subprocess.check_output(
                    ["git", "log", "--all", "--format=%H", "--", str(relative)], cwd=root, text=True).splitlines()
                for commit in commits:
                    packed = subprocess.run(["git", "archive", commit, str(relative)], cwd=root, capture_output=True)
                    if packed.returncode:
                        continue
                    with tempfile.TemporaryDirectory(prefix="ethevals-stamp-") as directory:
                        with tarfile.open(fileobj=io.BytesIO(packed.stdout)) as archive:
                            archive.extractall(directory, filter="data")
                        task = Path(directory) / relative
                        if "sha256:" + Packager.compute_content_hash(task)[0] == row["task_hash"]:
                            cache[key] = task_hashes(task)
                            break
                if key not in cache:
                    raise ValueError(f"Cannot find task files for {row['task_id']} at {row['task_hash']}; no rows changed")
        hashes = cache[key]
        inputs = {**hashes["checks_inputs"], "@judge": row.get("judge")}
        stamped.append({**row, **hashes, "checks_inputs": inputs, "checks_hash": digest(inputs), "schema_version": 9})
    return stamped


def stamp_file(path: Path, root: Path) -> int:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    stamped = stamp_rows(rows, root)
    from .trial_rows import write_rows
    write_rows(path, stamped)
    return len(stamped)
