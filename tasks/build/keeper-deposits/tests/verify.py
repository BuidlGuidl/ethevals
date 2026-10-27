"""Build a fresh project and run keeper deposits against a private fork."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request

CHECKS = [check["name"] for check in (
    dict(name="compile"), dict(name="deposit_lands"), dict(name="signature_used_first"),
    dict(name="two_pending"), dict(name="safe_depositor"), dict(name="no_replay"), dict(name="forged_deposit"),
)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--context", type=Path, default=Path("/chain/chain_context.json"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier"))
    parser.add_argument("--tools", type=Path, default=Path("/opt"))
    parser.add_argument("--deps", type=Path, default=Path("/opt/deposit-verifier"))
    parser.add_argument("--forge-std", type=Path, default=Path("/opt/solidity/lib/forge-std/src"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.tools))
    from forge_checks import project_remappings

    records = {name: {"passed": False, "reason": "Compilation or helper import failed."} for name in CHECKS}
    with tempfile.TemporaryDirectory(prefix="keeper-deposits-") as directory:
        root = Path(directory)

        def ignore(directory, names):
            return [name for name in names if name in {".git", "out", "cache"} or (Path(directory) / name).is_symlink()]

        project = root / "workspace"
        shutil.copytree(args.workspace, project, ignore=ignore)
        context = json.loads(args.context.read_text())
        remappings = [line for line in project_remappings(project) if not line.startswith("forge-std/=")]
        remappings.append(f"forge-std/={args.forge_std.resolve()}/")
        settings = tomllib.loads((project / "foundry.toml").read_text()).get("profile", {}).get("default", {})
        build_options = "".join(
            f"{key} = {json.dumps(settings[key])}\n"
            for key in ("optimizer", "optimizer_runs", "via_ir", "evm_version") if key in settings
        )
        (root / "foundry.toml").write_text(
            '[profile.default]\nsrc = "workspace/src"\nout = "workspace/out"\nlibs = []\n'
            'test = "absent-tests"\nscript = "absent-scripts"\n'
            'solc = "0.8.30"\nffi = false\nauto_detect_remappings = false\n'
            + "remappings = " + json.dumps(remappings) + "\n"
            + build_options
        )
        build = subprocess.run(
            ["forge", "build", "--root", str(root)], capture_output=True, text=True, timeout=180,
        )
        (args.output / "build.log").write_text(build.stdout + build.stderr)
        artifact_path = project / "out/KeeperDeposits.sol/KeeperDeposits.json"
        helper_path = project / "script/deposits.ts"
        if build.returncode or not artifact_path.exists() or not helper_path.exists():
            (args.output / "checks.json").write_text(json.dumps(records, indent=2) + "\n")
            return

        # A second Anvil forks the filtered sidecar. Only this private copy receives chain controls.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        fork = subprocess.Popen(
            ["anvil", "--fork-url", context["rpcUrl"], "--chain-id", "1", "--host", "127.0.0.1", "--port", str(port),
             "--accounts", "0", "--silent"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(200):
                try:
                    request = urllib.request.Request(url, b'{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}',
                                                     {"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=1) as response:
                        if json.load(response).get("result") == "0x1":
                            break
                except OSError:
                    pass
                if fork.poll() is not None:
                    raise RuntimeError("The private fork exited before it started.")
                time.sleep(0.1)
            else:
                raise RuntimeError("The private fork did not start.")
            context["rpcUrl"] = url
            (project / "chain_context.json").write_text(json.dumps(context))
            env = {key: value for key, value in os.environ.items() if key not in {
                "MAINNET_RPC_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY",
            }}
            env["VERIFIER_DEPS"] = str(args.deps.resolve())
            env["RPC_URL"] = url
            run = subprocess.run(
                ["node", "--import", str(args.deps / "node_modules/tsx/dist/loader.mjs"),
                 str(Path(__file__).with_name("deposits.mjs")), str(project), str(artifact_path), str(args.output.resolve())],
                cwd=project, env=env, capture_output=True, text=True, timeout=360,
            )
            (args.output / "deposits.log").write_text(run.stdout + run.stderr)
            if run.returncode:
                raise RuntimeError(f"The deposit checks exited {run.returncode}. See deposits.log.")
        finally:
            fork.terminate()
            try:
                fork.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fork.kill()
                fork.wait()


if __name__ == "__main__":
    main()
