# Production Readiness Report

**Assessment date:** 27 November 2026
**Decision:** **NOT PRODUCTION READY. Live broker orders are disabled.**
**Scope:** Repository and local evidence reviewed for engineering, data, risk, security, paper trading, broker boundaries, and operations.

## Executive assessment

This is a local NSE cash-equity research and paper-trading application. Python owns technical and sizing calculations; the local LLM does not control risk. The current tree contains no Kite adapter and no live order submission route. The forward simulator uses SQLite and completed-session bars. This is a useful safety boundary, but it does not establish live-trading readiness.

The most important blockers are missing five-year, point-in-time historical evidence; only one recorded forward paper session; no broker integration/reconciliation/mock order lifecycle; and incomplete daily/weekly/drawdown controls. A 2026-only NSE calendar also requires maintenance before 2027 sessions.

## Findings by severity

### Critical

- **No critical defect found that currently permits an actual order.** The repository has no broker submission code; `/api/health` advertises `orders_enabled=false`, and current paper workflows explicitly return `order_placed=false`.
- **Live-trading eligibility is absent.** Do not expose this application as a live trading system. The missing controls below are release blockers, not deferred live features.

### High

- **Local API controls added.** API data/mutation routes require a constant-time bearer token; all API routes reject non-loopback clients. This is single-user local authorization, not a multi-user identity system.
- **Account risk is incomplete.** A ₹1,500 aggregate cap is derived from three positions × ₹500 per position and enforced across sizing, forward paper, manual portfolio records, and simulated trades. Daily/weekly loss, drawdown, order-count, price-deviation, failure-attempt, and sector-concentration controls remain unimplemented.
- **Paper scan advancement had unsafe optional freshness metadata and a concurrent duplicate-session race.** The simulator now requires a matching fresh metadata file and acquires a SQLite immediate write transaction before checking/advancing a session.
- **Five-year validation is incomplete.** The available six-month replay has 12 trades, returned +1.31% net against Nifty 50 TRI +9.04%, with 1.13% max drawdown. Five years of point-in-time members, delisted/merged names, adjustment/action provenance, Nifty 500 TRI, and rolling walk-forward results are unavailable. Do not extrapolate this small sample.
- **Forward paper evidence is insufficient.** The status artifact records one completed session (27 Nov 2026) and zero trades. The requested 30+ calendar days/actual sessions have not elapsed.
- **NSE calendar coverage is only 2026.** Verify official holidays and special sessions for 2027 before scheduling or relying on expected-session calculations beyond the supported year.
- **Broker gates are entirely pending.** No read-only Kite adapter, simulator, broker reconciliation, durable broker order states, or kill switch has been verified.
- **The user-provided Kaggle dataset is not accepted as validation evidence.** Version 2 downloaded successfully. The two files span 2021-06 through 2026-06, include no point-in-time membership or TRI benchmark, and show significant missing OHLCV and zero-volume rows in the supposedly complete panel. Details and validation requirements are in [KAGGLE_DATASET_ASSESSMENT.md](KAGGLE_DATASET_ASSESSMENT.md). Data is stored in ignored local storage, not Git.

### Medium

- `ManualPositionRequest` and `ManualCloseRequest` accepted non-finite float values at schema validation; finite-only validation has been added.
- npm's production dependency audit could not reach `registry.npmjs.org` in this environment; no vulnerability result can be claimed.
- Frontend build succeeds but reports a ~508 kB minified JavaScript chunk warning.
- Startup suppresses database initialization exceptions and serves read-only scanner state; the health endpoint reports database availability. This behavior should be monitored and configuration errors should be made more explicit before deployment.
- Market data relies primarily on Yahoo Finance with official NSE bhavcopy fallback, and the published completion cutoff is a heuristic. Historical adjustment provenance and every zero-volume/missing-bar interpretation require further validation.

### Low

- Some dashboard/manual paper figures are explicitly simulated or recorded manually and are not broker-confirmed account facts. Keep those labels visible and never combine them with future broker P&L.
- Several operational artifacts and calendar/configuration updates remain manual and need a documented owner/cadence.

## Changes made in this readiness pass

- Forward paper simulation now fails closed when freshness metadata is omitted or mismatched.
- SQLite session check, book advancement, and session marker are serialized with `BEGIN IMMEDIATE`.
- Python sizing and forward paper entries enforce a ₹1,500 aggregate open-risk ceiling, in addition to the existing per-trade cap.
- Aggregate risk is also enforced for manual portfolio records and dashboard paper trades; PostgreSQL advisory transaction locks serialize these cap checks.
- API routes require a local bearer token and reject non-loopback peers; manual position/close schemas reject NaN and infinity.
- Added the companion readiness, security, risk, broker, order lifecycle, paper evaluation, deployment, incident, and release documents.
- Added a Kaggle download/inventory helper and assessed the downloaded version 2 archive. It is not sufficient for the requested walk-forward validation.

## Gate status

| Gate | Status | Evidence / gap |
| --- | --- | --- |
| 1. Engineering readiness | **Partial** | Post-change tests/build pass; daily/weekly/drawdown and several other risk controls remain absent; online dependency audit unavailable; broader security and operational review remains open. |
| 2. Historical validation | **Blocked** | Only six-month exploratory replay available; five-year point-in-time universe/history and rolling OOS results missing. |
| 3. Forward paper validation | **Not met** | One recorded session; 30+ days and adequate trade observations pending. |
| 4. Broker integration | **Not started** | No Kite read-only adapter, mock broker lifecycle, or reconciliation evidence. |
| 5. Limited live pilot | **Unavailable** | Requires independent review and separate explicit decision after all prior gates. |

## Baseline verification

Verification after the safety changes:

- `.venv/bin/python -m unittest discover -v` — **52 passed**.
- `.venv/bin/python -m unittest discover -s backend/tests -v` — **9 passed**.
- `npm run build` from `frontend/` — **passed**, with ~510 kB JavaScript chunk warning.
- `.venv/bin/python -m pip check` — **passed**, no broken requirements.
- `.venv/bin/python -m compileall -q backend risk_manager.py forward_paper.py paper_trading.py trading_pipeline.py tools` — **passed**.
- `sh -n scripts/run_local_api.sh` and `git diff --check` — **passed**.
- `npm audit --omit=dev --json` from `frontend/` — **not completed**: network DNS failure reaching npm registry.

An additional API security test attempt using Starlette's `TestClient` first revealed `httpx` is not installed; tests were rewritten to exercise the middleware directly, so no dependency was added. Passing tests do not validate strategy profitability or live safety.

## Decision

Keep this release paper/research-only. Do not add or enable live order submission. Resolve the High findings, obtain and validate the missing historical data, accumulate honest forward paper evidence, complete broker mock/reconciliation work, and obtain an independent review before considering any live pilot.
