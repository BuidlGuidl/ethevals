"""Upload checked Harbor jobs and keep links outside their checked contents."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import UUID

from harbor.auth.credentials import API_KEY_ENV_VAR

from .job_config import JobSettings
from .secret_check import RECEIPT, check_folder, check_output, require_checked, secret_values, stage_artifact


def upload_hub(output: Path, config: JobSettings) -> None:
    if not config.hub or not os.environ.get(config.hub.key_env, "").strip():
        print("Harbor Hub upload skipped: configure hub and its key variable.", file=sys.stderr)
        return
    receipt = output / "hub.json"
    uploaded = json.loads(receipt.read_text()) if receipt.exists() else {}
    secrets = secret_values(config, [])
    for board in sorted((output / "jobs").glob("*/board.json")):
        folder = board.parent
        try:
            require_checked(folder)
            # Harbor leaves resumable upload state on failure. Keep it outside checked files.
            with tempfile.TemporaryDirectory(prefix="ethevals-hub-") as temporary:
                snapshot = Path(temporary) / "jobs" / folder.name
                shutil.copytree(folder, snapshot)
                require_checked(snapshot)
                names, digest = check_folder(snapshot, secrets)
                if names:
                    check_output(Path(temporary), secrets)
                    shutil.copyfile(snapshot / RECEIPT, folder / RECEIPT)
                    continue
                job_id = str(UUID(json.loads((snapshot / "result.json").read_text())["id"]))
                trials = {str(UUID(json.loads(path.read_text())["id"]))
                          for path in snapshot.glob("*/result.json")}
                subprocess.run(["harbor", "upload", str(snapshot), "--org", config.hub.org, "--public"],
                               check=True, timeout=600, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env={**os.environ, API_KEY_ENV_VAR: os.environ[config.hub.key_env]})
            uploaded[folder.name] = {"digest": digest, "job_id": job_id, "trials": sorted(trials)}
            temporary = receipt.with_suffix(".tmp")
            temporary.write_text(json.dumps(uploaded, sort_keys=True) + "\n")
            temporary.replace(receipt)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # The CLI can print credentials from a failed request. Never relay its output.
            print("Harbor Hub upload skipped or failed; the trial keeps its release trajectory.", file=sys.stderr)
    if (output / "public").is_dir():
        from .trial_rows import recover_rows, write_rows

        stage_artifact(output, output / "public")
        if receipt.exists():
            shutil.copyfile(receipt, output / "public/hub.json")
        write_rows(output / "public/rows.jsonl", recover_rows(output / "public"))


def trial_url(folder: Path) -> str | None:
    job = folder.parent
    receipt = job.parent.parent / "hub.json"
    if not receipt.exists():
        return None
    try:
        uploaded = json.loads(receipt.read_text())[job.name]
        require_checked(job)
        if uploaded["digest"] != json.loads((job / RECEIPT).read_text())["digest"]:
            return None
        job_id = str(UUID(json.loads((job / "result.json").read_text())["id"]))
        trial_id = str(UUID(json.loads((folder / "result.json").read_text())["id"]))
        if uploaded["job_id"] == job_id and trial_id in uploaded["trials"]:
            return f"https://hub.harborframework.com/jobs/{job_id}/trials/{trial_id}"
    except (OSError, ValueError, KeyError):
        pass
    return None
