#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Balancer V3 Vault findings

## 1. A wrapper keeps the Vault's approval after an EXACT_IN wrap

Severity: High

Location: pkg/vault/contracts/Vault.sol (_wrapWithBuffer, erc4626BufferWrapOrUnwrap)

When the buffer can't serve a wrap, _wrapWithBuffer calls underlyingToken.forceApprove(wrappedToken, amountToDeposit) and then wrappedToken.deposit. The EXACT_IN branch never sets the approval back to zero (the EXACT_OUT branch, which calls mint, does). Anyone can wrap through a buffer for a wrapper contract they deployed. A wrapper whose deposit takes nothing keeps the allowance, and after the session ends it calls transferFrom on the Vault to take the underlying tokens, which belong to other pools' liquidity. Repeating this drains every token the attacker can name as an underlying.

## 2. collectAggregateFees leaves reserves above the real balance

Severity: High

Location: pkg/vault/contracts/VaultAdmin.sol (collectAggregateFees); pkg/vault/contracts/Vault.sol (_updateReservesAfterWrapping, erc4626BufferWrapOrUnwrap)

collectAggregateFees is permissionless. It approves the ProtocolFeeController, which pulls the accumulated fees out of the Vault, but _reservesOf for those tokens is not reduced. After that the Vault's balance is lower than its recorded reserves. _updateReservesAfterWrapping derives the amounts moved during a wrap or unwrap from _reservesOf before and balanceOf after, so the missing fee amount is treated as underlying the wrapper consumed or released, and the caller is credited with it. An attacker uses a pool that takes a 100% fee paid to its creator to create a large gap, collects the fees, then wraps or unwraps through a wrapper they control to withdraw the gap, draining the token from the Vault.

## 3. A wrapper can switch its buffer's underlying token

Severity: High

Location: pkg/vault/contracts/Vault.sol (erc4626BufferWrapOrUnwrap, _wrapWithBuffer); pkg/vault/contracts/VaultAdmin.sol (addLiquidityToBuffer, removeLiquidityFromBuffer)

The Vault reads the underlying token from wrappedToken.asset() on every call. erc4626BufferWrapOrUnwrap only compares it with _bufferAssets when that entry is set, and addLiquidityToBuffer sets it only on the first deposit. The attacker's wrapper first reports a worthless token as its asset and returns 0 from convertToShares, so EXACT_IN wraps go through the buffer branch and add the worthless token to the uninitialized buffer's raw balance. The wrapper then switches asset() to DAI, the attacker calls addLiquidityToBuffer with zero amounts to initialize the buffer with DAI as its asset and receive shares sized by the wrapper, and removeLiquidityFromBuffer pays out the buffer's balance in DAI. The same works for any token the Vault holds.
REPORT
