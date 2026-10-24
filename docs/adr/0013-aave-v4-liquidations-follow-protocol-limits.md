---
status: accepted
---

# Aave V4 liquidation checks follow protocol limits

The Aave V4 task's borrower D has WETH and WBTC collateral.
Taking WBTC first leaves D above health factor 1.0, so the protocol refuses another liquidation below its target.
The task accepts D when its debt clears or its health factor reaches 1.0.
A and B keep the target requirement, and B also has a whole-debt check.
This keeps A's check against V3's 50% repayment limit.

The report parser accepts common field names, token aliases, and amounts with units.
It ignores entries without a positive repayment, so a skipped-borrower note does not fail the report.
Every positive repayment still needs one matching chain event within 1%.
Reward Kit still requires every check to pass.
