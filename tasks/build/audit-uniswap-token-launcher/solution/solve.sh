#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Token Launcher findings

## 1. Reserved tokens are locked when the auction does not graduate

Severity: Critical

Location: src/distributionContracts/LBPStrategyBasic.sol (validate, migrate); src/TokenLauncher.sol (distributeToken)

distributeToken deploys LBPStrategyBasic and sends it the whole supply. onTokensReceived forwards the auction share to the auction and keeps reserveSupply for the pool. The reserve can only leave through migrate(), and migrate() relies on the price and amounts stored by validate(), which only the auction can call and which it calls only from sweepCurrency after the auction graduates. When the auction does not graduate, the auction refunds bidders and returns unsold tokens to tokensRecipient, but validate() is never called. LBPStrategyBasic has no sweep or withdraw function, so reserveSupply is locked in the strategy for good.

## 2. Unchecked auction recipients break the hand-off to the pool

Severity: High

Location: src/distributionContracts/LBPStrategyBasic.sol (constructor, onTokensReceived, validate)

The auction parameters are an opaque bytes value the launch creator supplies. LBPStrategyBasic stores them and passes them to the auction factory without decoding them, so fundsRecipient, fundsRecipientData and tokensRecipient are never checked. The flow needs fundsRecipient to be the strategy and fundsRecipientData to call validate(). If fundsRecipient is another address or the data is empty, sweepCurrency sends the raised currency there, validate() never runs, migrate() cannot open the pool and reserveSupply stays stuck even after a successful auction. If tokensRecipient is set to the strategy, the unsold tokens returned by sweepUnsoldTokens are locked in it, because it cannot transfer them.
REPORT
