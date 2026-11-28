# PKScreener-AI phase status

Updated 27 November 2026 (IST, 21:38). This is a local NSE cash-equity research and decision-support project. Python owns calculations and risk rules; the local language model only explains them. No F&O, leverage, paid API, or automated order placement is enabled.

| Phase | Status | Evidence / remaining work |
| --- | --- | --- |
| 1. Market data and universe | Built | The inspected universe contains 496 raw symbols and 461 qualified symbols. |
| 2. Technical analysis | Built | Swing, VCP, trend, relative strength, breakout, and entry/exit modules are implemented. |
| 3. Risk management | Improved; more limits pending | ₹100,000 capital, ₹60,000 deployment limit, ₹500 max risk per trade, ₹1,500 aggregate open risk, ₹20,000 max allocation per position, maximum three positions, and 2–20 session holding guide. Daily/weekly loss, drawdown, sector, and order-rate limits remain absent. |
| 4. Reliable full-universe screener | Live validation passed | Completed-session guard, bounded retries/backoff, OHLCV validation, one benchmark download per scan, recent-window Yahoo retry, safe completed-session cache, and official NSE bhavcopy fallback. Full 461-symbol scan passed freshness for 27 Nov 2026 with zero analysis errors. Seven newer listings were explicitly excluded for fewer than 253 aligned sessions. |
| 5. Historical backtest | Six-month exploratory replay completed; five-year remains pending | Built a dated 524-symbol EQ bundle and ran 26 May–26 Nov 2026: 12 trades, +1.31% net, 58.3% wins, 2.69 profit factor, −1.13% max drawdown. Nifty 50 TRI returned +9.04%. Evidence is low confidence (95% Wilson win-rate interval 31.95%–80.67%). This does not satisfy the five-year validation phase. |
| 6. Local AI analyst | Implemented | Ollama/Qwen explanations are guarded by deterministic Python results; malformed AI values are replaced or rejected. |
| 7. Dashboard and alerts | Implemented; local authorization added | Dashboard renders freshness, forward paper book/history, and the read-only historical replay metrics/trade ledger. API access requires a local token and loopback peer. PostgreSQL is currently unavailable, so the separate manual watchlist/portfolio panel is disabled. The paper book uses SQLite. Telegram is unconfigured; real orders are disabled. |
| 8. Paper trading | Forward simulator and dashboard implemented; month-long evaluation pending | Daily fresh scans feed an idempotent local paper journal with three paper modes, next-session entries, automated exits, cost-aware scorecard, and history. The LaunchAgent is installed for weekdays at 17:30 IST. One fresh session is recorded (27 Nov); it produced zero eligible trades. Accumulate at least one month of completed sessions. Kite orders remain disabled. |

## Latest full-universe run

Run: 27 November 2026 at 17:20 IST  
Expected completed NSE session: 27 November 2026  
Freshness: `FRESH`  
Universe: 461 qualified symbols; all stock rows and the benchmark aligned to 27 November  
Source mix: 461 Yahoo Finance auto-adjusted OHLCV rows  
Analysis errors: 0  
Insufficient-history exclusions: 7  
Setup watch: 9; risk-eligible confirmed breakouts: 0

The forward paper book recorded session 1 (27 November), with zero queued, opened, or closed trades. The setup-watch names were not promoted to trades.

Artifacts:
- `screening_results_20261127_172010.csv`
- `breakout_candidates_20261127_172010.csv`
- `scan_metadata_20261127_172010.json`

## Verification

- Python deterministic suite: 52 passed, including completed-session trimming, stale/mismatched data, invalid OHLCV, risk caps, paper freshness/idempotency/concurrency, retry bounds, fallback behavior, win/loss metrics, and assumptions-file output.
- Backend suite: 9 passed, including local-token authorization, loopback enforcement, finite numeric validation, and scan-service freshness behavior.
- Frontend production build: passed.
- Local API health and dashboard endpoints returned HTTP 200; health reports `FRESH`, database available, `local_only=true`, `orders_enabled=false`, and Telegram unconfigured.
- Browser-rendered dashboard verified `FRESH · 2026-11-27`, one paper session, zero eligible setups, and zero trades.
- Python syntax compilation and frontend production build passed after the paper workflow changes. The build reports a non-blocking ~502 kB JavaScript chunk warning.
- `GET /api/forward-paper` returned HTTP 200 with the 27 Nov session and zero trades. The weekday 17:30 LaunchAgent is loaded; today’s run was started manually before its scheduled trigger.
- No live orders or Telegram alerts were sent.
- Frontend API token is stored in tab-scoped session storage. `scripts/run_local_api.sh` creates a local token in ignored `.env` on first run.

## Data source and assumptions

- Yahoo Finance remains the primary free source. It can omit or delay bars, so it is not treated as authoritative.
- Official NSE daily security bhavcopy is the fallback for completed daily EQ bars. It does not provide a free live intraday feed. Scans are therefore completed-session research scans, not live quotes.
- Zerodha Kite Connect's market-data access is paid; it was not installed, authorized, or used because the project scope is free/local.
- The 16:00 IST daily publication cutoff is a heuristic. The expected-session calendar must be updated and checked against NSE's official holiday/special-session announcements as they are published.
- Corporate-action adjustment continuity is guarded, but complete historical adjustment provenance still needs validation before long-window backtests.

## Historical evaluation work

- Verified that the local market cache is not a backtest bundle: representative bars begin in November 2024, contain auto-adjusted OHLCV, and do not include the required dividend-action column or sourced point-in-time membership.
- Added average net winning trade, average absolute net losing trade, their ratio, and explicit win/loss counts alongside profit factor.
- Each saved run now writes a separate assumptions JSON with the metrics, trades, and equity curve.
- Focused deterministic backtest tests: 11 passed.
- Attempted the requested 26 Nov 2021–26 Nov 2026 run; it stopped before simulation because the five-year bundle was absent.
- Official Nifty Indices historical reports expose Nifty 50 price and Total Return Index reports. The date-range form rejects requests longer than one year, so benchmark data must be acquired in bounded slices. The requested window was visible, but no CSV was saved locally during this check.
- The Nifty 500 page exposes a current constituent download, while the official press-release archive documents reconstitution changes. A complete, reconciled point-in-time history still needs to be assembled; daily security bars and cash actions also need complete coverage and provenance before the engine can be certified.

### Six-month exploratory replay (26 May–26 November 2026)

- Built `data/backtest/` with 524 historical EQ symbols, 525 dated membership intervals, 410 Nifty 50 price/TRI sessions, and stock history covering the indicator warm-up.
- Used official NSE daily bhavcopies for dated series checks and replay execution bars; Yahoo Finance supplies longer split-adjusted history and action fields. Merger-delisted JBCHEPHARM history was recovered from NSE daily reports and its in-window dividend action from NSE corporate actions.
- NSE held a live cash session on Sunday 1 February 2026. Yahoo omitted it, so the missing warm-up session was reconciled to the NSE report; absent EQ rows are explicitly represented as flat zero-volume no-trade bars.
- Result: ₹1,00,000 to ₹1,01,306.16; +1.31% net versus Nifty 50 TRI +9.04%; 12 trades (7 wins, 5 losses); 58.33% win rate; 95% Wilson interval 31.95%–80.67%; profit factor 2.69; average win/loss 1.92; expectancy ₹108.85/trade; maximum drawdown −1.13%.
- This is exploratory evidence with a small trade count, not a validated success rate, forecast, or five-year backtest. The rule confidence score is not calibrated as a probability of profit.
- Saved metrics, assumptions, trade ledger, and daily equity curve under `data/backtest/results/`. Added a read-only `/api/backtest` route and historical replay section in the local dashboard.

## Remaining phases

1. Extend the sourced point-in-time EQ history, dividend actions, and benchmark from six months to the requested five-year period plus warm-up.
2. Run and review the survivorship-safe five-year backtest with the same disclosed costs and slippage assumptions; compare the strategy against the current exploratory result.
3. Accumulate at least one month of fresh forward paper sessions and review expectancy, win rate, profit factor, drawdown, and confidence calibration.
4. Add dividend cash-action accounting before interpreting paper P&L as total return.
5. Refresh/verify NSE holiday and special-session calendar coverage for 2027 before the year boundary.
6. Only after the paper review, design the separate Kite integration and live-order approval flow.


## Paper workflow implementation (27 November 2026)

- Added a persistent SQLite forward paper book that advances only after a fully fresh scan; it is idempotent by NSE session.
- Confirmed, risk-sized breakout setups store entry reference, structural stop, 2R target, planned quantity, and deterministic rule confidence. Only these eligible setups appear in the trade panel.
- Added manual, ask-on-low-confidence, and paper-auto modes. All modes remain simulated; manual approvals queue next-session simulation only.
- Entries use next-session open with adverse slippage; exits apply gap/stop/target/time rules, with stop-first handling when both levels are touched. Forward fills use raw official NSE EQ bars, and displayed plan levels are scaled into raw-price units. Statutory delivery charges are estimated; brokerage is assumed ₹0 and must be changed for a broker-specific comparison.
- Added trade-history and scorecard endpoints/UI and a weekday 17:30 macOS LaunchAgent installer. The screener default is now the full qualified universe.
- Live Kite execution remains disabled pending the requested month of paper evaluation.
- Historical 2021–present performance remains blocked: `data/backtest/` still lacks the required point-in-time universe and complete sourced history. The current-universe cache is not presented as a historical result.
- The owner-provided Kaggle dataset version 2 was downloaded and inspected in ignored local storage. It is not accepted for backtesting: it ends in June 2026, lacks dated index membership and TRI benchmark series, and contains 65,279 fully missing OHLCV rows plus 2,131 zero-volume rows in the “complete” file. See `KAGGLE_DATASET_ASSESSMENT.md`.

## Strategy intelligence and signal-quality review (28 November 2026)

- Fingerprinted the saved six-month baseline in `STRATEGY_BASELINE_SNAPSHOT.json`, including hashes of its metrics, assumptions, trade ledger, and equity curve. The new report generator fails if those source artifacts change and writes only to a unique experiment directory.
- Added deterministic, as-of-date-safe, non-gating measurements for VCP structure/volume, relative strength, breakout context, Nifty regime, and eligible-universe breadth. Added synthetic tests for date cutoffs and measurement behavior.
- Generated descriptive diagnostics for the existing 12 trades: MFE/MAE, 1R/2R and stop touches, regime, feature snapshots, and overlapping loss tags. These observations are exploratory and do not establish causes.
- Added a local-token-protected read-only `/api/strategy-intelligence` endpoint and dashboard panel. Backtest, forward-paper, and broker results remain distinct; no broker execution capability was introduced.
- **Validation outcome:** no strategy change passed validation. Retest/consolidation entries, alternate exits, feature ablations, and five-year walk-forward remain untested or blocked because the six-month sample has already been inspected and the data bundle lacks five-year point-in-time coverage plus warm-up. No win-rate improvement is claimed.
- Details: `STRATEGY_INTELLIGENCE_IMPLEMENTATION_PLAN.md`, `STRATEGY_FAILURE_ANALYSIS.md`, and `STRATEGY_EXPERIMENT_COMPARISON.md`.
