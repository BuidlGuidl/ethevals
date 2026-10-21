"""Run Forge and write the check records shared by every verifier tool."""
import json
import re
import argparse
import os
from pathlib import Path
import posixpath
import shutil
import subprocess
import tempfile


def forge_results(stdout: str) -> dict:
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        output = None
    checks = {}
    suites = {}
    if isinstance(output, dict):
        for suite, result in output.items():
            if not isinstance(result, dict):
                continue
            for name, test in result.get("test_results", {}).items():
                name = name.partition("(")[0]
                if name in {"setUp", "constructor"}:
                    name = f"{suite.rsplit(':', 1)[-1]}.{name}"
                if name in suites:
                    raise RuntimeError(f"Duplicate Forge check {name!r} in suites {suites[name]!r} and {suite!r}.")
                suites[name] = suite
                passed = test["status"] == "Success"
                checks[name] = {
                    "passed": passed,
                    "reason": "Test passed." if passed else " ".join(str(test.get("reason") or test["status"]).split()),
                }
    return checks


def compiler_diagnostic(stdout: str, stderr: str) -> str | None:
    lines = [line.strip() for line in (stdout + "\n" + stderr).splitlines()]
    reason = next((line for line in lines if re.match(r"^(?:Compiler)?Error \([0-9]+\):", line)), None)
    if reason is None:
        reason = next((line for line in lines if line.startswith("CompilerError:")), None)
    if reason is None:
        reason = next((line for line in lines if any(message in line.lower() for message in
                      ("incompatible versions", "no solc version exists"))), None)
    return reason


def forge_checks(stdout: str, stderr: str, returncode: int) -> tuple[bool, str, dict]:
    if returncode < 0 or returncode >= 128:
        raise RuntimeError(f"Forge terminated with exit code {returncode}.")
    checks = forge_results(stdout)
    if checks and returncode and all(check["passed"] for check in checks.values()):
        raise RuntimeError(f"Forge exited {returncode} after passing every test.")
    compiled = bool(checks)
    reason = compiler_diagnostic(stdout, stderr)
    if not compiled and reason is None:
        raise RuntimeError(f"Forge exited {returncode} without test results or a compiler diagnostic. {(stderr or stdout).strip()}")
    return compiled, "Compilation passed." if compiled else reason, checks


def project_remappings(workspace: Path) -> list[str]:
    files = [path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.is_file()]
    projects = sorted({str(Path(name).parent) for name in files
                       if Path(name).name in {"foundry.toml", "package.json"}},
                      key=lambda name: (-len(Path(name).parts), name))
    mappings = []
    for project in projects:
        root = "workspace" if project == "." else f"workspace/{project}"
        if (workspace / project / "foundry.toml").is_file():
            result = subprocess.run(["forge", "remappings", "--root", str(workspace / project)],
                                    capture_output=True, text=True, timeout=30,
                                    env={**os.environ, "FOUNDRY_OFFLINE": "true"})
            for line in result.stdout.splitlines() if result.returncode == 0 else []:
                left, separator, target = line.strip().partition("=")
                context, colon, prefix = left.rpartition(":")
                prefix = prefix if colon else left
                if not separator or prefix.startswith(("forge-std/", "ds-test/", "hardhat/console.sol")) or target.startswith("/"):
                    continue
                target = posixpath.normpath(f"{root}/{target}") + ("/" if target.endswith("/") else "")
                scoped = posixpath.normpath(f"{root}/{context}") if colon else root
                if target.startswith("workspace/") and (scoped == "workspace" or scoped.startswith("workspace/")):
                    mappings.append(f"{scoped}/:{prefix}={target}")
        mappings.append(f"{root}/:src/={root}/src/")
        modules = str(Path(project) / "node_modules") + "/"
        packages = set()
        for name in files:
            if name.startswith(modules):
                parts = name.removeprefix(modules).split("/")
                if not parts[0].startswith("."):
                    package = "/".join(parts[:2]) if parts[0].startswith("@") else parts[0]
                    if package not in {"forge-std", "ds-test"}:
                        packages.add(package)
        mappings.extend(f"{root}/:{package}/={root}/node_modules/{package}/" for package in sorted(packages))
        mappings.append(f"{root}/:hardhat/console.sol=/opt/solidity/lib/forge-std/src/console.sol")
    unique = {}
    for line in mappings:
        unique.setdefault(line.partition("=")[0], line)
    return [*sorted(unique.values(), key=lambda line: (
        -line.partition(":")[0].count("/"), -len(line.partition(":")[2].partition("=")[0]), line)),
        "forge-std/=/opt/solidity/lib/forge-std/src/", "hardhat/console.sol=/opt/solidity/lib/forge-std/src/console.sol"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, default=Path("/tests"))
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--context", type=Path, default=Path("/chain/chain_context.json"))
    parser.add_argument("--private-context", type=Path, default=Path("/private/private_chain_context.json"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="forge-checks-") as directory:
        root = Path(directory)
        # Do not follow agent symlinks while the verifier runs as root.
        def ignore_links(directory, names):
            return [name for name in names if (Path(directory) / name).is_symlink()]
        shutil.copytree(args.workspace, root / "workspace", ignore=ignore_links)
        shutil.copytree(args.tests, root / "tests")
        for source, name in ((args.context, "chain_context.json"), (args.private_context, "private_chain_context.json")):
            if source.exists():
                shutil.copyfile(source, root / name)
        config = Path("/opt/verify-foundry.toml").read_text()
        config += "remappings = " + json.dumps(project_remappings(root / "workspace")) + "\n"
        config += 'fs_permissions = [{access = "read", path = "chain_context.json"}, {access = "read", path = "private_chain_context.json"}]\n'
        if args.context.exists():
            config += "[rpc_endpoints]\nchain = " + json.dumps(json.loads(args.context.read_text())["rpcUrl"]) + "\n"
        (root / "foundry.toml").write_text(config)
        result = subprocess.run(["forge", "test", "--json", "--no-storage-caching"],
                                cwd=root, capture_output=True, text=True, timeout=600)
        (args.output / "forge.stdout").write_text(result.stdout)
        (args.output / "forge.stderr").write_text(result.stderr)
        compiled, reason, checks = forge_checks(result.stdout, result.stderr, result.returncode)
        if not compiled:
            for path in args.tests.rglob("*.t.sol"):
                for name in re.findall(r"\bfunction\s+(test\w*)\s*\(", path.read_text()):
                    checks[name] = {"passed": False, "reason": "Compilation failed."}
        checks = {"compile": {"passed": compiled, "reason": reason}, **checks}
        (args.output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
        (args.output / "reward.txt").write_text(str(int(all(check["passed"] for check in checks.values()))) + "\n")


if __name__ == "__main__":
    main()
