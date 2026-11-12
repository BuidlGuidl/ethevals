"""Restore a saved Build workspace as the agent step of a normal trial."""
import inspect
import json
from pathlib import Path
import shlex
import shutil

from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions


def restore_workspace(source, workspace, excluded):
    import os
    from pathlib import Path
    import shutil
    import subprocess

    source, workspace = Path(source), Path(workspace)
    for child in workspace.iterdir():
        if child.name not in {*excluded, "chain_context.json"}:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    for child in source.iterdir():
        if child.name in excluded or child.name == "chain_context.json":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, workspace / child.name, symlinks=True)
        else:
            shutil.copy2(child, workspace / child.name, follow_symlinks=False)
    if (workspace / "package.json").is_file():
        subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=workspace, check=True,
                       env={**os.environ, "CI": "true"})


class SavedWorkOptions(AgentOptions):
    trial: str


class SavedWorkAgent(BaseAgent):
    options_model = SavedWorkOptions

    @staticmethod
    def name():
        return "saved-work"

    def version(self):
        return "1.0.0"

    async def setup(self, environment):
        pass

    async def run(self, instruction, environment, context):
        trial = Path(self.options.trial)
        manifest = json.loads((trial / "artifacts/manifest.json").read_text())
        entry, = [entry for entry in manifest if entry["source"].rstrip("/") == "/workspace" and entry.get("service") in {None, "main"}]
        if entry["status"] != "ok":
            raise ValueError("The saved workspace is unavailable.")
        saved_context = {}
        for name in ("chain_context.json", "fixture.json"):
            file = trial / "verifier" / name
            if file.is_file():
                saved_context = json.loads(file.read_text())
                break
        await environment.upload_dir(trial / entry["destination"], "/tmp/regrade-workspace")
        # Older fixtures also hold check output. Restore only fields from the public context.
        script = (
            "import json\nfrom pathlib import Path\n"
            "context = Path('/chain/chain_context.json')\n"
            "fresh = json.loads(context.read_text())\n"
            f"saved = {saved_context!r}\n"
            "fresh.update({key: value for key, value in saved.items() if key in fresh and key != 'rpcUrl'})\n"
            "context.write_text(json.dumps(fresh) + '\\n')\n")
        if saved_context:
            result = await environment.service_exec("python3 -c " + shlex.quote(script), service="chain", user="root")
            if result.return_code:
                raise RuntimeError(f"Saved context restore failed: {result.stderr}\n{result.stdout}")
        script = (
            "import os\nfrom pathlib import Path\n"
            "owner = Path('/workspace').stat()\n"
            "staging = Path('/tmp/regrade-workspace')\n"
            "for file in [staging, *staging.rglob('*')]: os.chown(file, owner.st_uid, owner.st_gid, follow_symlinks=False)\n"
            "context = Path('/workspace/chain_context.json')\n"
            "Path('/logs/verifier').mkdir(parents=True, exist_ok=True)\n"
            "if context.exists(): Path('/logs/verifier/chain_context.json').write_bytes(context.read_bytes())\n")
        result = await environment.exec("python3 -c " + shlex.quote(script), user="root")
        if result.return_code:
            raise RuntimeError(f"Saved context restore failed: {result.stderr}\n{result.stdout}")
        script = inspect.getsource(restore_workspace) + (
            f"\nrestore_workspace('/tmp/regrade-workspace', '/workspace', {entry.get('exclude', [])!r})\n")
        result = await environment.exec("python3 -c " + shlex.quote(script))
        if result.return_code:
            raise RuntimeError(f"Saved work restore failed: {result.stderr}\n{result.stdout}")
        trajectory = trial / "agent/trajectory.json"
        if trajectory.is_file():
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(trajectory, self.logs_dir / "trajectory.json")
            await environment.upload_file(trajectory, "/logs/agent/trajectory.json")
