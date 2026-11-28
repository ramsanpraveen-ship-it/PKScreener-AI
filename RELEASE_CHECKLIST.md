# Release Checklist

## Current release decision

**Not production-ready. Keep live orders disabled. Do not publish this release as live-trading software.** Push is pending user review/approval.

## Engineering and safety

- [x] Re-run full root Python (**52 passed**) and backend suites (**9 passed**).
- [x] Test concurrent paper-session processing and finite API inputs.
- [x] Add local bearer-token authentication and enforced loopback-peer restriction.
- [x] Add tests for mandatory freshness metadata, aggregate open risk, and API authorization boundaries.
- [ ] Specify and test daily/weekly loss, drawdown, order count/notional/deviation, attempt, and sector limits.
- [ ] Review database backup/restore and structured redacted logs.
- [ ] Run online dependency vulnerability scan; current npm audit was blocked by DNS/network access.

## Evidence gates

- [ ] Five-year point-in-time historical data, delisted/merged names, corporate actions, and Nifty 50/500 TRI validated. The downloaded Kaggle archive does not satisfy these needs; see [KAGGLE_DATASET_ASSESSMENT.md](KAGGLE_DATASET_ASSESSMENT.md).
- [ ] Rolling chronological walk-forward and untouched OOS results generated reproducibly.
- [ ] At least 30 calendar days of real NSE-session forward paper records reviewed; do not backfill.
- [ ] Read-only broker integration, mock order lifecycle, reconciliation, kill switch, and security review completed.
- [ ] Independent reviewer signs off all gates.

## Prohibited until separate decision

- [ ] No real Kite credentials or order path in this release.
- [ ] No public network exposure.
- [ ] No automatic promotion to live mode.
- [ ] No push to the remote until user review and explicit approval.
