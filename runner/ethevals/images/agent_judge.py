"""Prepare file inputs and a fresh user settings directory for an agent judge."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys


def prepare(inputs, *, directory=Path("/judge"), home=Path("/root/judge-home")):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    submission = directory / "submission"
    shutil.rmtree(submission, ignore_errors=True)
    submission.mkdir(mode=0o700)
    for source in inputs:
        shutil.copyfile(source, submission / source.name)
    shutil.rmtree(home, ignore_errors=True)
    (home / ".claude").mkdir(mode=0o700, parents=True)
    shutil.copyfile("/opt/judge-settings.json", home / ".claude/settings.json")
    return home


def environment(home):
    names = {"PATH", "LANG", "PLAYWRIGHT_BROWSERS_PATH", "LD_LIBRARY_PATH", "FONTCONFIG_FILE",
             "CLAUDE_CODE_OAUTH_TOKEN", "REWARDKIT_JUDGE", "REWARDKIT_MODEL", "REWARDKIT_REASONING_EFFORT",
             "REWARDKIT_LOG_DIR", "REWARDKIT_FORCE_SUBSCRIPTION", "CAST_RPC_URL", "ETH_RPC_URL"}
    result = {name: value for name, value in os.environ.items()
              if name in names or name.startswith("ETHEVALS_REGRADE_")}
    result.update(HOME=str(home), PYTHON_DOTENV_DISABLED="1", DISABLE_AUTOUPDATER="1",
                  CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="1")
    result["PATH"] = "/root/.local/bin:/usr/local/bin:" + result.get("PATH", "/usr/bin:/bin")
    return result


if __name__ == "__main__":
    home = prepare([Path(name) for name in sys.argv[1:]])
    binary = shutil.which("rewardkit")
    output = Path("/logs/verifier")
    try:
        subprocess.run([binary, "/tests"], env=environment(home), check=True)
        details = json.loads((output / "reward-details.json").read_text())

        def errors(value):
            if isinstance(value, dict):
                return bool(value.get("error")) or any(errors(child) for child in value.values())
            return isinstance(value, list) and any(errors(child) for child in value)

        if errors(details):
            raise RuntimeError("The judge failed. See reward-details.json.")
    except BaseException:
        (output / "reward.json").unlink(missing_ok=True)
        raise
    finally:
        projects = home / ".claude/projects"
        if projects.exists():
            shutil.copytree(projects, output / "judge-transcripts", dirs_exist_ok=True)
