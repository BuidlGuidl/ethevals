"""Lint task folders and prove their solutions through Harbor."""
from pathlib import Path
import json
import os
import re
import shutil
import tomllib

from rewardkit.models import JudgeTomlConfig

from harbor.models.task.task import Task
import toml
import yaml

from .checks import read_reward
from .images.tag import BUILD_INPUTS, image_tag
from .job_config import JobSettings, load_job

AGENT_WORDS = re.compile(r"\b(?:epochs?|graders?|rubrics?|scores?|benchmarks?|evals?|being\s+tested)\b", re.IGNORECASE)
SERVICE_KEYS = {"image", "build", "init", "command", "entrypoint", "working_dir", "user",
                "environment", "networks", "volumes", "depends_on", "healthcheck", "mem_limit", "cpus"}


def task_judges(path: Path) -> dict[Path, JudgeTomlConfig]:
    judges = {}
    for file in sorted((path / "tests").rglob("*.toml")):
        document = tomllib.loads(file.read_text())
        if "judge" in document or "criterion" in document:
            judges[file] = JudgeTomlConfig.model_validate(document)
    return judges


def task_host_variables(path: Path) -> list[str]:
    """Read required host variables from compose interpolation."""
    names = set()
    for compose in sorted(path.rglob("*compose.y*ml")):
        def read(value):
            if isinstance(value, str):
                value = value.replace("$$", "")
                for match in re.finditer(r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)", value):
                    name = match[1]
                    if not re.match(r"\$\{" + name + r":\?[^{}\s][^{}]*\}", value[match.start():]):
                        raise ValueError(f"{compose}: {name}: host variables must use ${{{name}:?message}}")
                    names.add(name)
            elif isinstance(value, dict):
                for key, child in value.items():
                    read(key)
                    read(child)
            elif isinstance(value, list):
                for child in value:
                    read(child)

        read(yaml.safe_load(compose.read_text()))
    return sorted(names)


def lint_task(path: Path, config: JobSettings | None = None) -> None:
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"{item}: symlinks are forbidden in task folders")
    for name in ("task.toml", "instruction.md", "tests/test.sh", "solution/solve.sh"):
        if not (path / name).is_file():
            raise ValueError(f"{path / name}: required file is missing")
    task = Task(path)
    if task.config.task is None:
        raise ValueError(f"{path / 'task.toml'}: [task] must declare name and description")
    if task.config.task.org != "buidlguidl":
        raise ValueError(f"{path / 'task.toml'}: [task].name must use the buidlguidl org")
    if not task.config.task.description.strip():
        raise ValueError(f"{path / 'task.toml'}: [task].description must be a nonempty line")
    if task.config.metadata.get("pillar") != path.parent.name:
        raise ValueError(f"{path / 'task.toml'}: metadata.pillar must match the parent folder {path.parent.name!r}")
    if "area" in task.config.metadata:
        area = task.config.metadata["area"]
        if not isinstance(area, str) or not area.strip():
            raise ValueError(f"{path / 'task.toml'}: metadata.area must be a nonempty string")
    config = config or load_job()
    credentials = config.credential_names()
    for name in task_host_variables(path):
        if name in credentials:
            raise ValueError(f"{path / 'task.toml'}: {name} is a job credential; tasks cannot request it")
    judges = task_judges(path)
    if task.config.verifier.env != ({config.judge.key_env: "${" + config.judge.key_env + "}"} if judges else {}):
        raise ValueError(f"{path / 'task.toml'}: verifier.env must declare only the required judge key when a judge exists")
    names = set()
    for file, judge in judges.items():
        if judge.judge.atif_trajectory != "/logs/agent/trajectory.json":
            raise ValueError(f"{file}: the judge must read the ATIF trajectory /logs/agent/trajectory.json")
        if judge.judge.guard not in {"flag", "penalize"}:
            raise ValueError(f"{file}: the judge guard must be flag or penalize")
        if judge.scoring.aggregation != "all-pass" or judge.judge.weight <= 0:
            raise ValueError(f"{file}: criteria must count toward all-pass")
        for criterion in judge.criterion:
            if not criterion.name or not criterion.name.strip() or criterion.name in names:
                raise ValueError(f"{file}: every criterion needs a unique, nonempty name")
            names.add(criterion.name)
            if criterion.type != "binary" or criterion.optional or criterion.weight <= 0:
                raise ValueError(f"{file}: criteria must be required binary checks with positive weights")
        for directory in [file.parent, *file.parent.parents]:
            reward = directory / "reward.toml"
            document = tomllib.loads(reward.read_text()) if reward.exists() else {}
            aggregates = document.get("reward", [])
            root = directory == path / "tests"
            if (not aggregates or any(item.get("aggregation") != "all-pass"
                    or any(weight <= 0 for weight in item.get("weights", {}).values()) for item in aggregates)
                    or root and not any(item.get("name") == "reward" for item in aggregates)):
                raise ValueError(f"{reward}: judge criteria and tests must contribute to all-pass reward")
            if root:
                break
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
            pins = {"ghcr.io/buidlguidl/" + image_tag(image=name) for name in BUILD_INPUTS}
            repositories = {pin.split(":")[0] for pin in pins}
            if image.split(":")[0] in repositories and image not in pins:
                raise ValueError(f"{item}: shared image pin {image} differs from its build inputs; update the task pin")
    for compose in path.rglob("*compose.y*ml"):
        document = yaml.safe_load(compose.read_text())

        if not isinstance(document, dict) or set(document) - {"services", "volumes", "networks", "name"}:
            raise ValueError(f"{compose}: only services, volumes, networks, and name are allowed")
        volumes = document.get("volumes") or {}
        for name, volume in volumes.items():
            if volume not in ({}, None):
                raise ValueError(f"{compose}: volume {name}: host mounts are forbidden; use a plain named volume")
        for name, network in (document.get("networks") or {}).items():
            network = network or {}
            if (set(network) - {"internal", "external", "name"}
                    or type(network.get("external", False)) is not bool
                    or network.get("name", name) == "host" or "$" in network.get("name", name)):
                raise ValueError(f"{compose}: network {name}: host networks and network driver options are forbidden")
        for name, service in document.get("services", {}).items():
            if not isinstance(service, dict):
                raise ValueError(f"{compose}: service {name}: must be a mapping")
            if extra := set(service) - SERVICE_KEYS:
                raise ValueError(f"{compose}: service {name}: forbidden options {sorted(extra)}; privileged containers and host mounts are forbidden")
            environment = service.get("environment", {})
            if not isinstance(environment, dict) or any(value is None for value in environment.values()):
                raise ValueError(f"{compose}: service {name}: use explicit values for the environment")
            build = service.get("build")
            if build:
                build = {"context": build} if isinstance(build, str) else build
                if extra := set(build) - {"context", "dockerfile", "additional_contexts", "args", "target"}:
                    raise ValueError(f"{compose}: service {name}: forbidden build options {sorted(extra)}")
                arguments = build.get("args", {})
                if not isinstance(arguments, dict) or any(value is None for value in arguments.values()):
                    raise ValueError(f"{compose}: service {name}: use explicit values for build arguments")
                context = (compose.parent / build.get("context", ".")).resolve()
                inputs = [context, context / build.get("dockerfile", "Dockerfile")]
                extra = build.get("additional_contexts", {})
                extra = dict(item.split("=", 1) for item in extra) if isinstance(extra, list) else extra
                inputs.extend((compose.parent / value).resolve() for value in extra.values())
                if any("$" in str(item) for item in inputs):
                    raise ValueError(f"{compose}: service {name}: build paths must be literal and stay inside the task folder")
                if any(not item.resolve().is_relative_to(path.resolve()) for item in inputs):
                    raise ValueError(f"{compose}: service {name}: build inputs must stay inside the task folder")
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
        missing = [name for name in task_host_variables(path) if not os.environ.get(name)]
        if missing:
            print(f"{path}: skipped oracle and nop runs because {', '.join(missing)} is unset.", flush=True)
        else:
            available.append(path)
    if not available:
        return
    originals = {}
    for path in available:
        staged = output / "tasks" / path.parent.name / path.name
        shutil.copytree(path, staged)
        originals[staged.resolve()] = path
        judges = task_judges(staged)
        if judges:
            print(f"{path}: criteria skipped in the free check; the judge needs a paid API call.", flush=True)
            for file in judges:
                file.unlink()
            for reward in (staged / "tests").rglob("reward.toml"):
                document = tomllib.loads(reward.read_text())
                for aggregate in document.get("reward", []):
                    aggregate.pop("weights", None)
                if reward.parent != staged / "tests" and not any(reward.parent.rglob("*.py")):
                    document.pop("reward", None)
                reward.write_text(toml.dumps(document))
    paths = list(originals)
    names = {}
    for agent, expected in (("oracle", True), ("nop", False)):
        config = JobConfig(
            job_name=agent, jobs_dir=output, n_concurrent_trials=1, quiet=True,
            agents=[{"name": agent, "override_timeout_sec": 1200}],
            verifier={"env": {load_job().judge.key_env: ""}},
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
            rewards, checks = read_reward(result_path.parent / "verifier")
            checks_path = result_path.parent / "verifier/reward-details.json"
            path = originals[Path(result["config"]["task"]["path"]).resolve()]
            if expected:
                names[path] = set(checks)
            elif set(checks) != names.get(path):
                raise ValueError(f"{checks_path}: oracle and nop runs must write the same check names")
            passed = all(check["passed"] for check in checks.values())
            saved = (result.get("verifier_result") or {}).get("rewards")
            if saved != rewards or rewards["reward"] != int(expected) or passed != expected:
                raise ValueError(f"{result_path}: {agent} run must give reward {int(expected)} with matching checks")
            print(f"{path}: {agent} reward {int(expected)}; checks: {checks_path}")
