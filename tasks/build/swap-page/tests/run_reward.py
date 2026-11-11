"""Run the page judge, then chain checks, then RewardKit's all-pass reward."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request

sys.path.insert(0, "/opt")
from agent_judge import environment, prepare
from rewardkit.models import JudgeTomlConfig
from rewardkit.runner import (_build_judge_reward, _discover_layout, _evaluate_layout,
                              _flatten_layout, _write_outputs)


def main():
    tests = Path("/tests")
    output = Path("/logs/verifier")
    for name in ("reward.json", "reward.txt", "reward-details.json", "session.json"):
        (output / name).unlink(missing_ok=True)
    home = prepare([])
    clean = environment(home)
    clean["PATH"] = "/tests/bin:" + clean["PATH"]
    os.environ.clear()
    os.environ.update(clean)
    os.environ["PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS"] = "1"
    code = Path("/judge/submission")
    shutil.copytree("/workspace", code, dirs_exist_ok=True, symlinks=True,
                    ignore=shutil.ignore_patterns("node_modules", "dist", ".git"))
    chain_context = code / "chain_context.json"
    chain_context.unlink(missing_ok=True)
    shutil.copyfile("/chain/chain_context.json", chain_context)
    with (output / "session.log").open("w") as log:
        child = subprocess.Popen(["node", "/tests/session.mjs"], stdout=log, stderr=log,
                                 env={key: value for key, value in clean.items() if key != "CLAUDE_CODE_OAUTH_TOKEN"})
        try:
            deadline = time.monotonic() + 360
            while not (output / "session.json").is_file():
                if child.poll() is not None:
                    raise RuntimeError("The wallet session failed to start. See session.log.")
                if time.monotonic() >= deadline:
                    raise RuntimeError("The wallet session timed out during setup.")
                time.sleep(0.1)
            session = json.loads((output / "session.json").read_text())
            os.environ["ETH_RPC_URL"] = session["rpc"]
            os.environ["CAST_RPC_URL"] = session["rpc"]
            text = (tests / "prompt.md").read_text().replace("<url>", session["origin"])
            text = text.replace("<address>", session["wallet"]).replace("<rpc url>", session["rpc"])
            (tests / "prompt-rendered.md").write_text(text)
            page = None
            if (tests / "page.toml").is_file():
                config = JudgeTomlConfig.model_validate(tomllib.loads((tests / "page.toml").read_text()))
                page = _build_judge_reward(tests / "page.toml", config, tests, code, "page")
                page.run()
                detail = page.to_detail_dict(page.score)
                (output / "judge-details.json").write_text(json.dumps(detail, indent=2) + "\n")
                if any(score.error for score in page.scores) or (page.guard_score and page.guard_score.error):
                    raise RuntimeError("The page judge failed. See judge-details.json.")
            else:
                subprocess.run(["node", "/tests/solution-walk.mjs"], check=True)
            request = urllib.request.Request(session["control"] + "/finish", b"[]")
            with urllib.request.urlopen(request, timeout=360) as response:
                response.read()
            layout = _discover_layout(tests, code)
            for reward in _flatten_layout(layout):
                if reward.judge is None:
                    reward.run()
                elif page is not None:
                    for name in ("scores", "judge_output", "warnings", "usage", "judge_logs", "guard_score"):
                        setattr(reward, name, getattr(page, name))
            values, details = _evaluate_layout(layout)
            _write_outputs(output / "reward.json", values, details)
        finally:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            projects = home / ".claude/projects"
            if projects.exists():
                shutil.copytree(projects, output / "judge-transcripts", dirs_exist_ok=True)
            browser_evidence = Path("/judge/.playwright-mcp")
            if browser_evidence.exists():
                shutil.copytree(browser_evidence, output / "browser-evidence", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
