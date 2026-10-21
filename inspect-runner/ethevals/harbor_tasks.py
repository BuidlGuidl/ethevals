"""Lint task folders and prove their solutions through Harbor."""
from pathlib import Path
import json
import os
import re

from harbor.models.task.task import Task
import yaml

from .images.tag import image_tag

AGENT_WORDS = re.compile(r"\b(?:epochs?|graders?|rubrics?|scores?|benchmarks?|evals?|being\s+tested)\b", re.IGNORECASE)


def lint_task(path: Path) -> None:
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"{item}: symlinks are forbidden in task folders")
    for name in ("task.toml", "instruction.md", "tests/test.sh", "solution/solve.sh"):
        if not (path / name).is_file():
            raise ValueError(f"{path / name}: required file is missing")
    task = Task(path)
    required = task.config.metadata.get("required_env", [])
    if not isinstance(required, list) or any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name) for name in required
    ):
        raise ValueError(f"{path / 'task.toml'}: metadata.required_env must list environment variable names")
    visible = [path / "instruction.md", *(path / "environment").rglob("*")]
    for item in visible:
        if not item.is_file():
            continue
        try:
            text = item.read_text()
        except UnicodeDecodeError:
            continue
        if match := AGENT_WORDS.search(text):
            raise ValueError(f"{item}: agent-visible text contains forbidden word {match.group()!r}")
        for image in re.findall(r"ghcr\.io/buidlguidl/ethevals-[\w:.-]+", text):
            pins = {"ghcr.io/buidlguidl/" + image_tag(image=name) for name in ("chain", "quiz")}
            if image not in pins:
                raise ValueError(f"{item}: shared image pin {image} differs from its build inputs; update the task pin")
    for compose in path.rglob("*compose.y*ml"):
        document = yaml.safe_load(compose.read_text())
        if not isinstance(document, dict) or set(document) - {"services", "volumes", "networks", "name"}:
            raise ValueError(f"{compose}: only services, volumes, networks, and name are allowed")
        volumes = document.get("volumes") or {}
        for name, volume in volumes.items():
            if volume not in ({}, None):
                raise ValueError(f"{compose}: volume {name}: host mounts are forbidden; use a plain named volume")
        for name, service in document.get("services", {}).items():
            build = service.get("build")
            if build:
                build = {"context": build} if isinstance(build, str) else build
                context = (compose.parent / build.get("context", ".")).resolve()
                inputs = [context, context / build.get("dockerfile", "Dockerfile")]
                extra = build.get("additional_contexts", {})
                extra = dict(item.split("=", 1) for item in extra) if isinstance(extra, list) else extra
                inputs.extend((compose.parent / value).resolve() for value in extra.values())
                if any(not item.resolve().is_relative_to(path.resolve()) for item in inputs):
                    raise ValueError(f"{compose}: service {name}: build inputs must stay inside the task folder")
            if service.get("privileged", False) is not False:
                raise ValueError(f"{compose}: service {name}: privileged containers are forbidden")
            if "extends" in service or "volumes_from" in service:
                raise ValueError(f"{compose}: service {name}: inherited containers and mounts are forbidden")
            for volume in service.get("volumes", []):
                source = volume.split(":")[0] if isinstance(volume, str) else volume.get("source")
                kind = "volume" if isinstance(volume, str) else volume.get("type")
                if kind != "volume" or source not in volumes:
                    raise ValueError(f"{compose}: service {name}: host mounts are forbidden; use a declared named volume")


async def free_check(paths: list[Path], output: Path) -> None:
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    if output.exists():
        raise ValueError(f"{output}: use a fresh output directory for each free check")
    available = []
    for path in paths:
        missing = [name for name in Task(path).config.metadata.get("required_env", []) if not os.environ.get(name)]
        if missing:
            print(f"{path}: skipped oracle and nop runs because {', '.join(missing)} is unset.", flush=True)
        else:
            available.append(path)
    paths = available
    if not paths:
        return
    for path in paths:
        if (path / "tests/criteria.md").is_file():
            print(f"{path}: criteria skipped in the free check; the judge needs a paid API call.", flush=True)
    names = {}
    for agent, expected in (("oracle", True), ("nop", False)):
        config = JobConfig(
            job_name=agent, jobs_dir=output, n_concurrent_trials=1, quiet=True,
            agents=[{"name": agent, "override_timeout_sec": 1200}],
            verifier={"override_timeout_sec": 1200},
            environment={"type": "docker"},
            tasks=[{"path": path.resolve()} for path in paths],
        )
        job = await Job.create(config)
        await job.run()
        results = sorted((output / agent).glob("*/result.json"))
        if len(results) != len(paths):
            raise ValueError(f"{output / agent}: expected {len(paths)} trial results, found {len(results)}")
        for result_path in results:
            result = json.loads(result_path.read_text())
            if result.get("exception_info"):
                raise ValueError(f"{result_path}: {result['exception_info']['exception_message']}")
            checks_path = result_path.parent / "verifier/checks.json"
            checks = json.loads(checks_path.read_text())
            if not isinstance(checks, dict) or not checks:
                raise ValueError(f"{checks_path}: write at least one named check")
            for name, check in checks.items():
                if not name or not isinstance(check, dict) or type(check.get("passed")) is not bool:
                    raise ValueError(f"{checks_path}: each named check needs a boolean passed field")
                reason = check.get("reason")
                if not isinstance(reason, str) or not reason.strip() or len(reason.splitlines()) != 1:
                    raise ValueError(f"{checks_path}: check {name}: write a one-line reason")
            path = Path(result["config"]["task"]["path"]).resolve()
            if expected:
                names[path] = set(checks)
            elif set(checks) != names.get(path):
                raise ValueError(f"{checks_path}: oracle and nop runs must write the same check names")
            passed = all(check["passed"] for check in checks.values())
            rewards = (result.get("verifier_result") or {}).get("rewards")
            if rewards != {"reward": int(expected)} or passed != expected:
                raise ValueError(f"{result_path}: {agent} run must give reward {int(expected)} with matching checks")
            print(f"{path}: {agent} reward {int(expected)}; checks: {checks_path}")
