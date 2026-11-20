// Board-only scoring settings for the Mixed and Weighted versions, kept here for the same reason as `taskTags`
// in areas.ts: settings in task.toml would change task hashes and retire every recorded trial.
// `partial` is the Mixed flag. `one` and `three` list the checks worth 1 and 3 points under Weighted.
// Entry checks are worth 0 everywhere and are not listed. A check left out of a listed task fails the build.
// A task left out scores as all or nothing under Mixed, unless its id starts with `build/audit-`,
// and its checks are worth 1 point each under Weighted.
export const taskScoring: Record<string, { partial?: true; one: string[]; three: string[] }> = {
  "act/treasury-eth-sale": {
    one: ["report_matches_chain", "nothing_left_behind"],
    three: ["fair_price", "swap_has_deadline", "swap_has_minimum", "once_per_quarter", "checks_receipt_status", "refusal_checks_price"],
  },
  "act/vault-v2-concentration-rebalance": {
    one: ["test_concentrationWithinPolicy", "test_fundsStayInvested", "test_nothingElseChanged"],
    three: ["test_withdrawalsStillServed"],
  },
  "act/vault-v2-market-exit": {
    one: ["test_depositorsStillServed", "test_nothingElseChanged"],
    three: ["test_vaultIsOutForGood", "test_strangerCannotReopenIt"],
  },
  "build/aave-savings-page": {
    partial: true,
    one: ["deposit_usdc", "withdraw_partial", "shows_deposit", "shows_apy"],
    three: ["withdraw_all", "deposit_usdt_leftover_allowance", "refuses_over_cap", "explains_supply_cap", "switches_and_continues"],
  },
  "build/creator-coins": {
    one: ["test_everyCoinOpensAtTenEth", "test_liquidityStaysPut", "test_onlyCreatorRedirects", "test_strangerCollectGetsNothing"],
    three: ["test_strangerCreatedPoolFirst", "test_feesAreThisCoins", "test_coinSideFeesPaidOut"],
  },
  "build/keeper-deposits": {
    one: ["deposit_lands", "no_replay", "forged_deposit"],
    three: ["signature_used_first", "two_pending", "safe_depositor"],
  },
  "build/signed-votes": {
    one: ["eoa_vote", "wrong_signer", "safe_vote", "safe_late_vote", "smart_wallet_deployed"],
    three: ["tampered_vote", "other_proposal", "other_chain", "safe_one_owner", "safe_onchain_approval", "safe_onchain_unapproved", "smart_wallet_new", "smart_wallet_new_reused"],
  },
  "build/swap-page": {
    partial: true,
    one: ["swaps_assets", "exact_approvals", "shows_received"],
    three: ["cut_only_on_swap", "finite_deadline", "native_eth", "routers_empty", "honors_minimum", "explains_price_change"],
  },
  "build/token-governor": {
    one: ["test_snapshotCanRunIt"],
    three: ["test_quorumCountsTheWholeSupply", "test_theDelayGuardsTheMoney", "test_lateVotesExtendTheVote"],
  },
  "build/token-launchpad": {
    one: ["test_opensAtCurvePrice", "test_curveStopsAfterGraduation", "test_lpIsBurned", "test_creatorEarnsFees", "test_everyoneCanSellBack", "test_curvesAreSeparate", "test_graduationSpendsOnlyItsCurve"],
    three: ["test_wethSyncedIntoPair", "test_tokensSyncedIntoPair", "test_strangerCannotSetOpeningPrice"],
  },
  "build/token-lending-market": {
    one: ["test_marketWorksAndBooksBalance"],
    three: ["test_interestChargedBeforeTheAction", "test_strayTokensChangeNothing", "test_roundingFavoursMarket", "test_liquidationFinishes", "test_badDebtWrittenOffAgainstLenders"],
  },
  "build/voting-page": {
    partial: true,
    one: ["lists_every_proposal", "status_and_tallies_match", "wrap_then_delegate", "canceled_status", "already_voted"],
    three: ["quorum_counts_for_only", "end_moves_with_late_quorum", "votes_at_snapshot"],
  },
};
