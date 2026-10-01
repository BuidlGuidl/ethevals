"""Forge setup, reference solutions, and finished-chain capture."""
from inspect_ai.util import sandbox
from inspect_ai.log import transcript

from .sandboxes import IMAGES, runner_exec, workspace_files

SETUP_TIMEOUT = 120


async def setup_script(evaluation, environments):
    box = environments["chain"]
    if "workspace/chain.json" in evaluation.files:
        raise ValueError("Setup cannot replace workspace/chain.json.")
    for name, data in evaluation.files.items():
        if name.startswith(("setup/", "workspace/")):
            await box.write_file("/eval/" + name, data)
    await box.write_file("/eval/foundry.toml", (IMAGES / "setup-foundry.toml").read_bytes())
    result = await runner_exec(box, ["forge", "script", "setup/setup.s.sol", "--broadcast", "--slow",
                                   "--rpc-url", "http://127.0.0.1:8546"], cwd="/eval", timeout=SETUP_TIMEOUT)
    if not result.success:
        raise RuntimeError(f"Chain setup exited {result.returncode}: {(result.stderr or result.stdout)[-4096:]}")
    chain = await box.read_file("/eval/chain.json", text=False)
    private = await box.read_file("/eval/private.json", text=False)
    await environments["default"].write_file("/workspace/chain.json", chain)
    await environments["scorer"].write_file("/workspace/chain.json", chain)
    await environments["scorer"].write_file("/workspace/private.json", private)
    # The public proxy never exposes these controls. Enforce automining after setup.
    result = await runner_exec(box, ["/usr/bin/python3", "-c",
        "import sys; sys.path.insert(0, '/opt'); from rpc_filter import rpc; "
        "rpc('anvil_setIntervalMining', [0]); rpc('evm_setAutomine', [True])"], cwd="/eval", timeout=60)
    if not result.success:
        raise RuntimeError("Cannot configure chain mining after setup.")


async def run_solution(evaluation, box):
    for name, data in evaluation.files.items():
        if name.startswith("solution/") and name != "solution/solution.s.sol":
            await box.write_file("/workspace/" + name.removeprefix("solution/"), data)
    if "solution/solution.s.sol" in evaluation.files:
        from .scorers import prepare_workspace, prepare_forge
        scorer = sandbox("scorer")
        root = await prepare_workspace(scorer, await workspace_files(), evaluation.files)
        await prepare_forge(root)
        for name, data in evaluation.files.items():
            if name.startswith("solution/"):
                await scorer.write_file("/workspace/" + name, data)
        result = await runner_exec(scorer, ["forge", "script", "solution/solution.s.sol", "--broadcast",
                                          "--rpc-url", "http://chain:8545"], cwd="/workspace", timeout=120)
        if not result.success:
            raise ValueError(f"Reference solution exited {result.returncode}: {(result.stderr or result.stdout)[-4096:]}")


async def capture_chain():
    box = sandbox("chain")
    # Wait for Anvil's mining mutex before the tests read state.
    result = await runner_exec(box, ["cast", "rpc", "--rpc-url", "http://127.0.0.1:8546", "evm_mine"], timeout=60)
    if not result.success:
        raise RuntimeError(f"Cannot settle chain mining: {result.stderr}")
    # Read bytes instead of Inspect's 20-line display.
    refusals = await box.read_file("/tmp/rpc-refusals.log", text=False)
    transcript().info({"rpc_refusals": refusals.decode("utf-8", errors="replace")})
