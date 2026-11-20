#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# OpenZeppelin Confidential Contracts findings

## 1. A failed callback refund is silent, so transferAndCall reports zero while the sender loses the tokens

Severity: Critical

Location: contracts/token/ConfidentialFungibleToken.sol (_transferAndCall, confidentialTransferAndCall, confidentialTransferFromAndCall); contracts/token/utils/ConfidentialFungibleTokenUtils.sol (checkOnTransferReceived)

_transferAndCall transfers `sent` to the recipient, calls onConfidentialTransferReceived, sets `transferred` to zero when the callback returns false, and refunds with _update(to, from, sent - transferred). The comment says the refund should never fail, and its result is not checked. A malicious recipient contract forwards the tokens to another address it controls inside the callback and returns false. The refund then lacks balance, and since FHE transfers that lack balance move an encrypted zero instead of reverting, nothing comes back. The call returns zero transferred, while the sender's balance is down by the full amount and the attacker holds the tokens. Any integration that trusts the return value (escrows, swaps, accounting) is misled.

## 2. The vesting wallet's released counter wraps around, so the owner vests early

Severity: High

Location: contracts/finance/VestingWalletConfidential.sol (release, releasable, vestedAmount)

_tokenReleased is a euint64, and release does released + amountSent with FHE.add, which wraps modulo 2^64 instead of reverting. vestedAmount computes the schedule on balance + released. The owner receives released tokens, sends them back to the wallet and calls release again; each cycle adds to the released counter until it passes 2^64 and wraps to a small value. With released now small, releasable is close to the whole schedule's share of the balance, and the owner withdraws tokens that have not vested yet. Example: at 75% of the duration, three release calls with one 35% top-up pay out 91% of the allocation.
REPORT
