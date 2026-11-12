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
