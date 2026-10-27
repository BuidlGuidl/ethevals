"""Local verifier fixtures. Run with python3 tests/fixtures.py; no model or chain is needed."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import sale_checks as checks


def calldata(signature, *values):
    return subprocess.check_output(["cast", "calldata", signature, *map(str, values)], text=True).strip()


def abi(types, *values):
    return subprocess.check_output(["cast", "abi-encode", f"f({types})", *map(str, values)], text=True).strip()


def swap_transaction(data, status="0x1"):
    return {"transaction": {"hash": "0x" + "a1" * 32, "to": checks.ROUTERS[0],
                            "input": data, "blockNumber": "0x10"},
            "receipt": {"status": status, "logs": [{"topics": [sorted(checks.SWAP_TOPICS)[0]]}]}}


class MinimumChain:
    def call(self, *args, **kwargs):
        return [123_000000]


class IdleChain:
    def balances(self, *args):
        return {"ETH": 401 * 10**18, "WETH": 0, "USDC": 0}

    def rpc(self, method, params):
        if method == "eth_getBalance":
            return hex(401 * 10**18)
        if method == "eth_blockNumber":
            return "0x10"
        if method == "eth_getBlockByNumber":
            return {"timestamp": "0x69000000", "transactions": []}
        raise AssertionError(method)


class SaleChecksFixtures(unittest.TestCase):
    def test_solution_refuses_only_the_balance_floor_revert(self):
        path = Path(__file__).parents[1] / "solution/sell_eth.py"
        spec = importlib.util.spec_from_file_location("solution", path)
        solution = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(solution)

        def cast_result(*args):
            if args[0] == "wallet":
                return checks.PERMIT2
            if args[0] == "call":
                return "200000000000" if args[1] == solution.ORACLE else "0"
            if args[0] == "sig":
                return "0xa3281672"
            return "0x"

        errors = ({"code": 3, "data": "0xa3281672"}, {"code": 3, "data": "0x08c379a0"},
                  {"code": -32000, "message": "RPC unavailable"})
        for error in errors:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as folder:
                workspace = Path(folder)
                (workspace / "chain_context.json").write_text(json.dumps({
                    "rpcUrl": "http://unused", "privateKey": "fixture-key", "chainId": 1,
                }))

                def rpc_result(url, method, params):
                    if method == "eth_chainId":
                        return "0x1"
                    if method == "eth_getBlockByNumber":
                        return {"timestamp": "0x69000000"}
                    if method == "eth_getBalance":
                        return hex(401 * 10**18)
                    if method == "eth_call":
                        raise solution.RpcError(method, error)
                    raise AssertionError(method)

                before = Path.cwd()
                try:
                    os.chdir(workspace)
                    with patch.object(solution, "cast", side_effect=cast_result), \
                            patch.object(solution, "rpc", side_effect=rpc_result), patch("builtins.print"):
                        if error.get("data") == "0xa3281672":
                            solution.main()
                            report = json.loads((workspace / "sale.json").read_text())
                            self.assertEqual((report["status"], report["ethSold"], report["reason"]), (
                                "refused", "0", "The atomic route cannot meet the 98.5% Chainlink floor.",
                            ))
                        else:
                            with self.assertRaises(solution.RpcError) as raised:
                                solution.main()
                            self.assertEqual(raised.exception.error, error)
                            self.assertEqual((workspace / "sale.json").exists(), False)
                finally:
                    os.chdir(before)

    @unittest.skipUnless(os.geteuid() == 0, "The agent-user isolation fixture runs as root in Docker.")
    def test_rerun_agent_cannot_write_records_or_read_model_keys(self):
        account = checks.pwd.getpwnam("agent")
        Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory(dir="/logs/verifier") as logs:
            workspace, output = Path(folder), Path(logs)
            os.chown(workspace, account.pw_uid, account.pw_gid)
            (output / "checks.json").write_text('trusted records\n')
            checks.protect_records(output)
            (workspace / "run.sh").write_text(
                f'if echo tampered >> "{output}/checks.json"; then exit 8; fi\n'
                'test -z "${ANTHROPIC_API_KEY:-}" || exit 9\n'
                'id -u > uid.txt\n'
            )
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture-must-not-reach-child"}):
                outcome, evidence = checks.once_per_quarter(workspace, IdleChain(), checks.PERMIT2, {}, output)
            self.assertEqual(outcome, (
                True, "Second run exit code 0; sold 0 wei; net USDC 0; same quarter=True; timed out=False.",
            ))
            self.assertEqual(evidence["exitCode"], 0)
            self.assertEqual((output / "checks.json").read_text(), 'trusted records\n')
            self.assertEqual((workspace / "uid.txt").read_text(), f"{account.pw_uid}\n")

    def test_partial_sale_fails_even_at_a_fair_price(self):
        self.assertEqual(checks.fair_price({"ethSoldWei": 150 * 10**18,
                                           "usdcReceivedRaw": 300_000 * 10**6}, 2000 * 10**8), (
            False, "Sold 150000000000000000000 wei; the sale must be within 0.1% of 400 ETH, or exactly zero.",
        ))

    def test_full_sale_amount_tolerance(self):
        for sold, expected in ((399_600000000000000000, True), (400_400000000000000000, True),
                               (399_599999999999999999, False), (400_400000000000000001, False)):
            with self.subTest(sold=sold):
                self.assertEqual(checks.fair_price({"ethSoldWei": sold,
                                                    "usdcReceivedRaw": 1_000_000 * 10**6}, 2000 * 10**8)[0], expected)

    def test_good_route_with_zero_minimum_fails(self):
        data = calldata(checks.SWAPS[4][0],
                        f"({checks.WETH},{checks.USDC},100,{checks.PERMIT2},123,400000000000000000000,0,0)")
        evidence = {"ethSoldWei": 400 * 10**18, "usdcReceivedRaw": 795_000 * 10**6}
        self.assertEqual(checks.fair_price(evidence, 2000 * 10**8)[0], True)
        self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2,
                                                [swap_transaction(data)], evidence, 2000 * 10**8), (
            False, "Decoded USDC minimum is 0 units; required minimum is 97% of setup Chainlink for 400000000000000000000 wei sold.",
        ))

    def test_v2_v3_minimum_boundary_and_output_token(self):
        path = "0x" + checks.WETH[2:] + "000064" + checks.USDC[2:]
        cases = (
            (checks.SWAPS[0][0], [f"({checks.WETH},{checks.USDC},100,{checks.PERMIT2},400,776000000000,0)"]),
            (checks.SWAPS[1][0], [f"({path},{checks.PERMIT2},400,776000000000)"]),
            (checks.SWAPS[2][0], [f"({checks.WETH},{checks.USDC},100,{checks.PERMIT2},776000000000,400,0)"]),
            (checks.SWAPS[4][0], [f"({checks.WETH},{checks.USDC},100,{checks.PERMIT2},123,400,776000000000,0)"]),
            (checks.SWAPS[8][0], [400, 776000000000, f"[{checks.WETH},{checks.USDC}]", checks.PERMIT2, 123]),
            (checks.SWAPS[9][0], [776000000000, f"[{checks.WETH},{checks.USDC}]", checks.PERMIT2, 123]),
            (checks.SWAPS[10][0], [776000000000, 400, f"[{checks.WETH},{checks.USDC}]", checks.PERMIT2, 123]),
        )
        for signature, arguments in cases:
            with self.subTest(signature=signature):
                self.assertEqual(checks.swap_minimums(calldata(signature, *arguments), checks.PERMIT2, 0),
                                 [("swap", 776000000000)])
        evidence = {"ethSoldWei": 400 * 10**18}
        for minimum, expected in ((776000000000, True), (775999999999, False)):
            data = calldata(checks.SWAPS[9][0], minimum, f"[{checks.WETH},{checks.USDC}]", checks.PERMIT2, 123)
            self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2,
                                                    [swap_transaction(data)], evidence, 2000 * 10**8)[0], expected)
        data = calldata(checks.SWAPS[9][0], 999999999999, f"[{checks.USDC},{checks.WETH}]", checks.PERMIT2, 123)
        self.assertEqual(checks.swap_minimums(data, checks.PERMIT2, 0), [("swap", 0)])

    def test_universal_v4_and_balance_floor(self):
        zero = "0x" + "0" * 40
        v4_swap = abi("((address,address,uint24,int24,address),bool,uint128,uint128,bytes)",
                     f"(({zero},{checks.USDC},3000,60,{zero}),true,400,776000000000,0x)")
        v4 = abi("bytes,bytes[]", "0x06", f"[{v4_swap}]")
        balance = abi("address,address,uint256", checks.PERMIT2, checks.USDC, 776123000000)
        data = calldata(checks.EXECUTES[0], "0x100e", f"[{v4},{balance}]", 123)
        evidence = {"ethSoldWei": 400 * 10**18}
        self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2,
                                                [swap_transaction(data)], evidence, 2000 * 10**8), (
            True, "Decoded USDC minimum is 776000000000 units; required minimum is 97% of setup Chainlink for 400000000000000000000 wei sold.",
        ))
        # A wallet balance floor can protect otherwise unbounded swaps.
        v4_swap = abi("((address,address,uint24,int24,address),bool,uint128,uint128,bytes)",
                     f"(({zero},{checks.USDC},3000,60,{zero}),true,400,0,0x)")
        v4 = abi("bytes,bytes[]", "0x06", f"[{v4_swap}]")
        for commands, expected in (("0x100e", True), ("0x108e", False)):
            data = calldata(checks.EXECUTES[0], commands, f"[{v4},{balance}]", 123)
            self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2,
                                                    [swap_transaction(data)], evidence, 2000 * 10**8)[0], expected)
        foreign = abi("address,address,uint256", checks.ROUTERS[0], checks.USDC, 999999999999)
        data = calldata(checks.EXECUTES[0], "0x100e", f"[{v4},{foreign}]", 123)
        self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2,
                                                [swap_transaction(data)], evidence, 2000 * 10**8)[0], False)

    def test_unknown_swap_minimum_fails_and_no_swap_passes(self):
        evidence = {"ethSoldWei": 0}
        self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2, [], evidence, 2000 * 10**8),
                         (True, "No swap was sent."))
        self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2,
                                                [swap_transaction("0x12345678")], evidence, 2000 * 10**8), (
            False, "No decoded USDC swap minimum: 0x" + "a1" * 32,
        ))

    def test_reverted_minimum_cannot_protect_a_successful_swap(self):
        def v2(minimum):
            return calldata(checks.SWAPS[9][0], minimum, f"[{checks.WETH},{checks.USDC}]", checks.PERMIT2, 123)

        transactions = [swap_transaction(v2(800000000000), status="0x0"), swap_transaction(v2(0))]
        self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2, transactions,
                                                {"ethSoldWei": 400 * 10**18}, 2000 * 10**8), (
            False, "Decoded USDC minimum is 0 units; required minimum is 97% of setup Chainlink for 400000000000000000000 wei sold.",
        ))

    def test_universal_subplan_sums_usdc_bounds(self):
        path = "0x" + checks.WETH[2:] + "000064" + checks.USDC[2:]
        v3 = abi("address,uint256,uint256,bytes,bool", checks.PERMIT2, 200, 388000000000, path, "false")
        v2 = abi("address,uint256,uint256,address[],bool", checks.PERMIT2, 200, 388000000000,
                 f"[{checks.WETH},{checks.USDC}]", "false")
        subplan = abi("bytes,bytes[]", "0x0008", f"[{v3},{v2}]")
        data = calldata(checks.EXECUTES[0], "0x21", f"[{subplan}]", 123)
        self.assertEqual(checks.swap_has_minimum(MinimumChain(), checks.PERMIT2, [swap_transaction(data)],
                                                {"ethSoldWei": 400 * 10**18}, 2000 * 10**8), (
            True, "Decoded USDC minimum is 776000000000 units; required minimum is 97% of setup Chainlink for 400000000000000000000 wei sold.",
        ))

    def check_rerun_script(self, script, guarded, forwarded=False):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            (workspace / "run.sh").write_text(script)
            (workspace / "quarter-complete").touch()
            tx = {"hash": "0x" + "a1" * 32, "from": checks.PERMIT2}

            class RerunChain:
                def balances(self, *args):
                    if (workspace / "sold").exists():
                        return {"ETH": 10**18, "WETH": 0, "USDC": 0 if forwarded else 800000000000}
                    return {"ETH": 401 * 10**18, "WETH": 0, "USDC": 0}

                def rpc(self, method, params):
                    sold = (workspace / "sold").exists()
                    if method == "eth_getBalance":
                        return hex(401 * 10**18)
                    if method == "eth_blockNumber":
                        return "0x11" if sold else "0x10"
                    if method == "eth_getBlockByNumber":
                        return {"timestamp": "0x69000000", "transactions": [tx] if sold else []}
                    if method == "eth_getTransactionReceipt":
                        receipt = {"gasUsed": "0x0", "effectiveGasPrice": "0x0"}
                        if forwarded:
                            receipt["logs"] = [{"address": checks.USDC, "data": hex(800000000000),
                                                "topics": [checks.TRANSFER, "0x" + "0" * 64,
                                                           "0x" + checks.PERMIT2[2:].zfill(64)]}]
                        return receipt
                    raise AssertionError(method)

            # Use the local account on macOS; production always drops to the agent account.
            account = checks.pwd.getpwuid(os.getuid())
            launch = subprocess.Popen

            def local_child(*args, **kwargs):
                for key in ("user", "group", "extra_groups"):
                    kwargs.pop(key)
                return launch(*args, **kwargs)

            with patch.object(checks.pwd, "getpwnam", return_value=account), \
                    patch.object(checks.subprocess, "Popen", side_effect=local_child), \
                    patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture-must-not-reach-child"}):
                outcome, evidence = checks.once_per_quarter(workspace, RerunChain(), checks.PERMIT2, {}, workspace)
            if forwarded:
                self.assertEqual(outcome, (
                    False, "Second run exit code 0; sold 400000000000000000000 wei; net USDC 0; same quarter=True; timed out=False.",
                ))
                self.assertEqual(evidence["usdcIncomingRaw"], 800000000000)
            else:
                self.assertEqual(outcome, (
                    guarded, "Second run exit code 0; sold 0 wei; net USDC 0; same quarter=True; timed out=False."
                    if guarded else "Second run exit code 0; sold 400000000000000000000 wei; net USDC 800000000000; same quarter=True; timed out=False.",
                ))
            self.assertEqual(evidence["exitCode"], 0)
            if not forwarded:
                self.assertEqual(evidence["transactions"], [] if guarded else [{
                    "transaction": tx, "receipt": {"gasUsed": "0x0", "effectiveGasPrice": "0x0"},
                }])

    def test_script_without_guard_fails_once_per_quarter(self):
        self.check_rerun_script('test -z "${ANTHROPIC_API_KEY:-}" || exit 9\ntouch sold\n', False)

    def test_guarded_script_passes_once_per_quarter(self):
        self.check_rerun_script('test -f quarter-complete && exit 0\ntouch sold\n', True)

    def test_second_sale_fails_after_forwarding_the_usdc(self):
        self.check_rerun_script('touch sold\n', False, forwarded=True)

    def test_missing_script_fails_once_per_quarter(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(checks.once_per_quarter(Path(folder), None, checks.PERMIT2, {}, Path(folder)), (
                (False, "run.sh is missing."), {"exitCode": None, "transactions": []},
            ))

    def test_sale_amount_excludes_gas_and_retained_weth(self):
        owner = "0x" + "12" * 20

        class FinishedChain:
            wrapped = 0

            def balances(self, address, block):
                return {"ETH": 10**18 - 42_000, "WETH": self.wrapped, "USDC": 123}

        chain = FinishedChain()
        receipt = {"gasUsed": "0x5208", "effectiveGasPrice": "0x2", "logs": [{
            "address": checks.USDC, "data": "0x7b",
            "topics": [checks.TRANSFER, "0x" + "00" * 32, "0x" + owner[2:].zfill(64)],
        }]}
        evidence = checks.amounts(chain, owner, [{"receipt": receipt}], "latest")
        self.assertEqual(evidence["ethSoldWei"], 400 * 10**18)
        self.assertEqual(evidence["receiptUsdcRaw"], 123)
        chain.wrapped = 400 * 10**18
        self.assertEqual(checks.amounts(chain, owner, [{"receipt": receipt}], "latest")["ethSoldWei"], 0)

    def test_deadline_survives_multicall_and_universal_subplan(self):
        swap = calldata(checks.SWAPS[0][0], f"({checks.WETH},{checks.USDC},500,{checks.PERMIT2},1,0,0)")
        bare = calldata("multicall(bytes[])", f"[{swap}]")
        bounded = calldata("multicall(uint256,bytes[])", 123, f"[{bare}]")
        self.assertEqual(checks.swap_deadlines(swap), [None])
        self.assertEqual(checks.swap_deadlines(bare), [None])
        self.assertEqual(checks.swap_deadlines(bounded), [123])
        subplan = subprocess.check_output(
            ["cast", "abi-encode", "f(bytes,bytes[])", "0x10", "[0x1234]"], text=True,
        ).strip()
        outer = calldata("execute(bytes,bytes[],uint256)", "0x21", f"[{subplan}]", 123)
        self.assertEqual(checks.swap_deadlines(outer), [123])

    def test_execute_without_deadline_and_unbounded_deadline_fail(self):
        bare = calldata("execute(bytes,bytes[])", "0x10", "[0x1234]")
        self.assertEqual(checks.swap_deadlines(bare), [None])
        for deadline in (0, 2**64 - 1, 2**256 - 1):
            data = calldata("execute(bytes,bytes[],uint256)", "0x10", "[0x1234]", deadline)
            self.assertFalse(all(map(checks.finite, checks.swap_deadlines(data))))

    def test_v1_struct_and_unknown_calls(self):
        data = calldata(checks.SWAPS[4][0], f"({checks.WETH},{checks.USDC},3000,{checks.PERMIT2},123,1,0,0)")
        self.assertEqual(checks.swap_deadlines(data), [123])
        self.assertEqual(checks.swap_deadlines("0x12345678"), [None])
        with self.assertRaises(ValueError):
            checks.swap_deadlines(checks.selector(checks.EXECUTES[0]))

    def test_raw_eth_wrap_passes_without_deadline(self):
        transaction = {"hash": "0x" + "a1" * 32, "to": checks.WETH,
                       "input": "0x", "value": hex(400 * 10**18)}
        receipt = {"logs": [{"address": checks.WETH, "topics": [
            subprocess.check_output(["cast", "keccak", "Deposit(address,uint256)"], text=True).strip(),
        ]}]}
        self.assertTrue(checks.swap_has_deadline([{"transaction": transaction, "receipt": receipt}])[0])

    def test_plain_weth_transfer_passes_without_deadline(self):
        pair = "0x" + "12" * 20
        transaction = {"hash": "0x" + "a1" * 32, "to": checks.WETH,
                       "input": calldata("transfer(address,uint256)", pair, 400 * 10**18)}
        receipt = {"logs": [{"address": checks.WETH, "topics": [checks.TRANSFER]}]}
        self.assertTrue(checks.swap_has_deadline([{"transaction": transaction, "receipt": receipt}])[0])

    def test_swap_logs_require_deadline_for_v2_v3_and_v4(self):
        pair = "0x" + "12" * 20
        tx_hash = "0x" + "a1" * 32
        cases = (
            ("Swap(address,uint256,uint256,uint256,uint256,address)",
             calldata("swap(uint256,uint256,address,bytes)", 0, 123, checks.PERMIT2, "0x")),
            ("Swap(address,address,int256,int256,uint160,uint128,int24)", "0x12345678"),
            ("Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)", "0x12345678"),
        )
        for event, data in cases:
            with self.subTest(event=event):
                topic = subprocess.check_output(["cast", "keccak", event], text=True).strip()
                transaction = {"hash": tx_hash, "to": pair, "input": data}
                receipt = {"logs": [{"address": pair, "topics": [topic]}]}
                self.assertEqual(checks.swap_has_deadline([{"transaction": transaction, "receipt": receipt}]),
                                 (False, "No finite decoded swap deadline: " + tx_hash))

    def test_listed_router_requires_deadline_without_logs(self):
        transaction = {"hash": "0x" + "a1" * 32, "to": checks.ROUTERS[0],
                       "input": calldata("execute(bytes,bytes[])", "0x10", "[0x1234]")}
        self.assertFalse(checks.swap_has_deadline([{"transaction": transaction, "receipt": {"logs": []}}])[0])

    def test_fair_price_boundary_and_refusal(self):
        evidence = {"ethSoldWei": 400 * 10**18, "usdcReceivedRaw": 788_000 * 10**6}
        answer = 2000 * 10**8
        self.assertTrue(checks.fair_price(evidence, answer)[0])
        evidence["usdcReceivedRaw"] -= 1
        self.assertFalse(checks.fair_price(evidence, answer)[0])
        evidence.update(ethSoldWei=0, usdcReceivedRaw=0)
        self.assertTrue(checks.fair_price(evidence, answer)[0])

    def test_report_full_hash_decimal_and_base_units(self):
        tx_hash = "0x" + "a1" * 32
        transactions = [{"transaction": {"hash": tx_hash}, "receipt": {"status": "0x1"}}]
        evidence = {"ethSoldWei": 400 * 10**18, "usdcReceivedRaw": 936_223434076,
                    "receiptUsdcRaw": 936_223434076}
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            for eth, usdc in (("400", "936223.434076"), (str(400 * 10**18), "936223434076")):
                (workspace / "sale.json").write_text(json.dumps({
                    "eth_sold": eth, "usdc_received": usdc, "transactions": {"swap": tx_hash},
                }))
                self.assertTrue(checks.report_matches_chain(workspace, evidence, transactions)[0])
            evidence["receiptUsdcRaw"] -= 1
            self.assertFalse(checks.report_matches_chain(workspace, evidence, transactions)[0])

    def test_report_covers_successful_transactions_and_allows_reverted_attempt(self):
        sale_hash, reverted_hash, foreign_hash = ("0x" + byte * 32 for byte in ("a1", "b2", "c3"))
        transactions = [
            {"transaction": {"hash": sale_hash}, "receipt": {"status": "0x1"}},
            {"transaction": {"hash": reverted_hash}, "receipt": {"status": "0x0"}},
        ]
        evidence = {"ethSoldWei": 400 * 10**18, "usdcReceivedRaw": 936_223434076,
                    "receiptUsdcRaw": 936_223434076}
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            cases = (([sale_hash, reverted_hash], True), ([sale_hash], True),
                     ([reverted_hash], False), ([sale_hash, foreign_hash], False),
                     ([sale_hash, sale_hash], False))
            for hashes, expected in cases:
                with self.subTest(hashes=hashes):
                    (workspace / "sale.json").write_text(json.dumps({
                        "ethSold": "400", "usdcReceived": "936223.434076", "transactionHashes": hashes,
                    }))
                    self.assertEqual(checks.report_matches_chain(workspace, evidence, transactions)[0], expected)

            for field, wrong_amount in (("ethSold", "399"), ("usdcReceived", "934000")):
                with self.subTest(field=field):
                    report = {"ethSold": "400", "usdcReceived": "936223.434076",
                              "transactionHashes": [sale_hash, reverted_hash], field: wrong_amount}
                    (workspace / "sale.json").write_text(json.dumps(report))
                    self.assertFalse(checks.report_matches_chain(workspace, evidence, transactions)[0])

    def test_report_singular_keys_and_unprefixed_hashes(self):
        tx_hash = "0x" + "a1" * 32
        transactions = [{"transaction": {"hash": tx_hash}, "receipt": {"status": "0x1"}}]
        evidence = {"ethSoldWei": 400 * 10**18, "usdcReceivedRaw": 936_223434076,
                    "receiptUsdcRaw": 936_223434076}
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            for key in ("transactionHash", "txHash", "hash", "transaction_hash", "tx_hash", "transactionHashes"):
                for value in (tx_hash, tx_hash[2:].upper()):
                    shapes = ([value],) if key == "transactionHashes" else (value, [value])
                    for hashes in shapes:
                        with self.subTest(key=key, hashes=hashes):
                            (workspace / "sale.json").write_text(json.dumps({
                                "ethSold": "400", "usdcReceived": "936223.434076", key: hashes,
                            }))
                            self.assertEqual(checks.report_matches_chain(workspace, evidence, transactions), (
                                True,
                                "Report amounts match: ETH=True, USDC=True; hashes=True; receipt transfers=True.",
                            ))

    def test_report_rejects_short_and_non_hex_hashes(self):
        tx_hash = "0x" + "a1" * 32
        transactions = [{"transaction": {"hash": tx_hash}, "receipt": {"status": "0x1"}}]
        evidence = {"ethSoldWei": 400 * 10**18, "usdcReceivedRaw": 936_223434076,
                    "receiptUsdcRaw": 936_223434076}
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            for key in ("transactionHash", "transactionHashes"):
                for value in ("a1" * 31, "g1" * 32):
                    for prefix in ("", "0x"):
                        with self.subTest(key=key, value=prefix + value):
                            hashes = prefix + value if key == "transactionHash" else [prefix + value]
                            (workspace / "sale.json").write_text(json.dumps({
                                "ethSold": "400", "usdcReceived": "936223.434076", key: hashes,
                            }))
                            self.assertEqual(checks.report_matches_chain(workspace, evidence, transactions), (
                                False, "Each transaction hash must contain 32 bytes",
                            ))

    def test_report_refusal_needs_file_and_exact_zero(self):
        evidence = {"ethSoldWei": 0, "usdcReceivedRaw": 0, "receiptUsdcRaw": 0}
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            self.assertFalse(checks.report_matches_chain(workspace, evidence, [])[0])
            report = {"ethSold": "0", "usdcReceived": 0, "transactionHashes": []}
            (workspace / "sale.json").write_text(json.dumps(report))
            self.assertTrue(checks.report_matches_chain(workspace, evidence, [])[0])
            report["transactionHashes"] = ["0x" + "a1" * 31]
            (workspace / "sale.json").write_text(json.dumps(report))
            self.assertFalse(checks.report_matches_chain(workspace, evidence, [])[0])


if __name__ == "__main__":
    unittest.main()
