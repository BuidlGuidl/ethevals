"""Plan and execute checks against saved work."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.error import HTTPError

from harbor.models.task.task import Task
from harbor.models.task.config import VerifierEnvironmentMode
from harbor.models.task.verifier_mode import resolve_task_verifier_mode, resolve_verifier_environment_definition

from .checks import read_details
from .harbor_tasks import task_judges
from .saved_work import SavedWorkGone, fetch_work
from .secret_check import check_output, remember_secrets
from .task_hashes import digest
from .trial_rows import fold_rows, write_rows, recover_regrades


def regrade_options(path: Path) -> dict:
    task = Task(path)
    kind = "concepts" if path.parent.name == "concepts" else None
    if (path.parent.name == "build" and resolve_task_verifier_mode(task.config) == VerifierEnvironmentMode.SEPARATE
            and not list((path / "environment").glob("*compose.y*ml"))
            and (path / "environment/foundry.toml").is_file()):
        kind = "contract"
    return {"kind": kind, "judge_files": [file.relative_to(path).as_posix() for file in task_judges(path)]}


def prepare_regrades(candidates: list[dict], cache: Path) -> tuple[list[dict], list[dict], list[dict]]:
    def prepare(item):
        try:
            work = fetch_work(item["source_row"], item["kind"], cache)
            if item["kind"] == "judge":
                details = read_details(Path(work["verifier"]))
                saved = [detail["judge"] for detail in details if detail.get("kind") in {"llm", "agent", "jev"}]
                for judge in task_judges(Path(item["task_path"])).values():
                    if not any((settings.get("files") or []) == (judge.judge.files or [])
                               and settings.get("atif_trajectory") == judge.judge.atif_trajectory
                               for settings in saved):
                        return None, {**item, "rerun_reason": "The judge's input selection changed."}, None
            return {**item, "saved_work": work}, None, None
        except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
            if isinstance(error, SavedWorkGone) or isinstance(error, HTTPError) and error.code in {404, 410}:
                return None, {**item, "rerun_reason": f"Saved work is gone: {error}"}, None
            return None, None, {**item, "defer_reason": f"Saved work fetch deferred: {error}"}
    with ThreadPoolExecutor(max_workers=8) as pool:
        prepared = list(pool.map(prepare, candidates))
    return tuple([entry[index] for entry in prepared if entry[index]] for index in range(3))


def run_regrades(items: list[dict], config, output: Path, previous: list[dict], secrets: dict) -> list[dict]:
    groups = {}
    for item in items:
        groups.setdefault((item["task_path"], item["kind"]), []).append(item)
    rows = previous
    for (task_path, kind), batch in groups.items():
        path = Path(task_path)
        key = digest([(item["source_row"], item["checks_hash"], item["retry"], item["checks_generation"])
                      for item in batch]).removeprefix("sha256:")[:24]
        job = output / "jobs" / key
        job.mkdir(parents=True, exist_ok=True)
        remember_secrets(job, secrets)
        (job / "board.json").write_text(json.dumps(batch[0]) + "\n")
        (job / "regrade.json").write_text(json.dumps(batch, indent=2) + "\n")
        try:
            if kind == "contract":
                for index, item in enumerate(batch):
                    destination = job / str(index)
                    if not (destination / "result.json").is_file():
                        subprocess.run(["harbor", "trial", "regrade", item["saved_work"]["trial"], "-p", str(path),
                                        "--trials-dir", str(job), "--trial-name", str(index)], check=True)
            else:
                task = Task(path)
                definition = resolve_verifier_environment_definition(task.config, task.paths)
                environment = definition.config if definition else task.config.environment
                image = environment.docker_image
                if not image:
                    image = "ethevals-regrade-" + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
                    subprocess.run(["docker", "build", "-t", image, str(definition.directory if definition else path / "environment")],
                                   check=True, capture_output=True)
                worker = Path(__file__).with_name("regrade_checks.py")
                command = ["docker", "run", "--rm", "--user", "root", "--network", "bridge" if any(item["judge_required"] for item in batch) else "none",
                           "--cpus", str(environment.cpus), "--memory", f"{environment.memory_mb}m",
                           "--entrypoint", "python3", "-v", f"{worker.resolve()}:/regrade.py:ro",
                           "-v", f"{(path / 'tests').resolve()}:/original-tests:ro", "-v", f"{job.resolve()}:/batch"]
                if any(item["judge_required"] for item in batch):
                    command += ["-e", config.judge.key_env, "-e", f"REWARDKIT_JUDGE={config.judge.model}",
                                "-e", f"REWARDKIT_REASONING_EFFORT={config.judge.effort}"]
                for index, item in enumerate(batch):
                    destination = job / str(index)
                    (destination / "agent").mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(item["saved_work"]["trajectory"], destination / "agent/trajectory.json")
                    verifier = item["saved_work"].get("verifier")
                    if verifier:
                        shutil.copytree(verifier, destination / "saved-verifier", dirs_exist_ok=True)
                subprocess.run([*command, image, "/regrade.py", "batch"], check=True)
        finally:
            check_output(output, secrets, require_inventory=True)
            rows = fold_rows(rows, recover_regrades(output))
            write_rows(output / "rows.jsonl", rows)
    return rows
