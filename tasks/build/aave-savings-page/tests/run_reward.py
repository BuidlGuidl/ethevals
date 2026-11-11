"""Run the page judge, then the chain checks, then RewardKit's all-pass reward."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import tomllib
import urllib.request

from agent_judge import environment, prepare
from install_judge import install
from rewardkit.models import JudgeTomlConfig, Score
from rewardkit.runner import (_build_judge_reward, _discover_layout, _evaluate_layout,
                              _flatten_layout, _write_outputs)

TESTS = Path("/tests")
OUTPUT = Path("/logs/verifier")
JUDGE = Path("/judge")


def copy_submission():
    """The judge starts one folder above the code, so files the agent wrote do not configure it."""
    JUDGE.mkdir(mode=0o700, parents=True, exist_ok=True)
    code = JUDGE / "submission"
    shutil.rmtree(code, ignore_errors=True)
    shutil.copytree("/workspace", code, symlinks=True, ignore=shutil.ignore_patterns("node_modules", "dist", ".git"))
    context = code / "chain_context.json"
    context.unlink(missing_ok=True)
    shutil.copyfile("/chain/chain_context.json", context)
    shutil.copyfile("/chain/chain_context.json", OUTPUT / "chain_context.json")
    return code


def did_not_compile(page):
    subprocess.run(["node", "--input-type=module", "-e", """
import fs from 'node:fs';
import { gradeSavings } from '/tests/checks.mjs';
const checks = JSON.parse(fs.readFileSync('/logs/verifier/checks.json', 'utf8'));
Object.assign(checks, gradeSavings({ compile: false }));
fs.writeFileSync('/logs/verifier/checks.json', JSON.stringify(checks) + '\\n');
"""], check=True)
    if page is not None:
        page.scores = [Score(name=criterion.name, value=0.0, raw=False, description=criterion.description,
                             reasoning="The project did not compile, so the judge did not open the page.")
                       for criterion in page.criteria]


def main():
    for name in ("reward.json", "reward.txt", "reward-details.json", "session.json", "judge-details.json"):
        (OUTPUT / name).unlink(missing_ok=True)
    judged = (TESTS / "page.toml").is_file()
    compiled = json.loads((OUTPUT / "checks.json").read_text())["compile"]["passed"]
    if compiled:
        install()
    home = prepare([])
    clean = environment(home)
    clean["PATH"] = "/tests/bin:" + clean["PATH"]
    clean["PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS"] = "1"
    os.environ.clear()
    os.environ.update(clean)
    code = copy_submission()
    page = None
    if judged:
        config = JudgeTomlConfig.model_validate(tomllib.loads((TESTS / "page.toml").read_text()))
        (TESTS / "prompt-rendered.md").write_text((TESTS / "prompt.md").read_text())
        page = _build_judge_reward(TESTS / "page.toml", config, TESTS, code, "page")
    child = None
    try:
        if not compiled:
            did_not_compile(page)
        else:
            log = (OUTPUT / "session.log").open("w")
            child = subprocess.Popen(["node", "/tests/session.mjs"], stdout=log, stderr=log,
                                     env={key: value for key, value in clean.items() if key != "CLAUDE_CODE_OAUTH_TOKEN"})
            deadline = time.monotonic() + 360
            while not (OUTPUT / "session.json").is_file():
                if child.poll() is not None:
                    raise RuntimeError("The wallet session failed to start. See session.log.")
                if time.monotonic() >= deadline:
                    raise RuntimeError("The wallet session timed out during setup.")
                time.sleep(0.1)
            session = json.loads((OUTPUT / "session.json").read_text())
            os.environ["ETH_RPC_URL"] = session["rpc"]
            if page is not None:
                text = (TESTS / "prompt.md").read_text().replace("<url>", session["origin"])
                text = text.replace("<address>", session["wallet"]).replace("<rpc url>", session["rpc"])
                (TESTS / "prompt-rendered.md").write_text(text)
                page.system_prompt = text
                page.run()
                (OUTPUT / "judge-details.json").write_text(json.dumps(page.to_detail_dict(page.score), indent=2) + "\n")
                if any(score.error for score in page.scores) or (page.guard_score and page.guard_score.error):
                    raise RuntimeError("The page judge failed. See judge-details.json.")
            else:
                subprocess.run(["node", "/tests/solution-walk.mjs"], check=True,
                               env={key: value for key, value in clean.items() if key != "CLAUDE_CODE_OAUTH_TOKEN"})
            request = urllib.request.Request(session["control"] + "/finish", b"[]")
            with urllib.request.urlopen(request, timeout=600) as response:
                response.read()
        layout = _discover_layout(TESTS, code)
        for reward in _flatten_layout(layout):
            if reward.judge is None:
                reward.run()
            elif page is not None:
                for name in ("scores", "judge_output", "warnings", "usage", "judge_logs", "guard_score"):
                    setattr(reward, name, getattr(page, name))
        values, details = _evaluate_layout(layout)
        _write_outputs(OUTPUT / "reward.json", values, details)
    finally:
        if child is not None:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        projects = home / ".claude/projects"
        if projects.exists():
            shutil.copytree(projects, OUTPUT / "judge-transcripts", dirs_exist_ok=True)
        browser_evidence = JUDGE / ".playwright-mcp"
        if browser_evidence.exists():
            shutil.copytree(browser_evidence, OUTPUT / "browser-evidence", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
