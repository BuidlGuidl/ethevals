"""Local verifier fixtures. Run with python3 tests/fixtures.py; no model or chain is needed."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import sale_checks as checks


def calldata(signature, *values):
    return subprocess.check_output(["cast", "calldata", signature, *map(str, values)], text=True).strip()


class SaleChecksFixtures(unittest.TestCase):
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
