# Historical and forward paper evaluation plan

## Purpose and safety boundary

Run the existing deterministic NSE cash-equity rules as research only. No broker connection or order placement is part of this phase. Keep the ₹100,000 capital, ₹60,000 deployment, ₹500 risk/trade, ₹20,000 position cap, three-position cap, and 2–20 session hold limits.

## Workstreams

1. **Historical walk-forward (2021–present):** a six-month exploratory replay for 26 May–26 November 2026 is now complete and saved under `data/backtest/results/`. It generated 12 trades and is explicitly low-confidence. To finish this workstream, extend the sourced point-in-time EQ membership, complete daily OHLCV plus dividend actions, Nifty 50 close, and official Nifty 50 TRI to five years plus warm-up. Validate date coverage, adjustment continuity, and source provenance. Run the existing `backtest_engine.py` only after its completeness gates pass. Never substitute current constituents or incomplete cache data silently.
2. **Daily forward paper book (one month minimum):** after each full-universe scan passes freshness, archive confirmed signals and their planned stop/2R target. On the next completed session, simulate entry at the official NSE EQ daily open with adverse slippage; size under the configured caps. Each fresh daily session checks stop/target (stop first if both touch), gap fills, and the 20-session time exit. Persist each session idempotently and expose open trades, closed trades, and cost-aware results in the dashboard. A stale/partial scan advances nothing. The installed weekday 17:30 macOS LaunchAgent runs the full-universe screener; the script skips non-session dates and data gates remain closed on stale data.
3. **Operations:** run the full scan after NSE EOD data is available on each trading day; retain scan, session, and trade audit artifacts. Review after at least one month of valid forward sessions and compare with the historical walk-forward result before considering broker integration.
4. **Later Kite stage:** only after review, separately design read-only market-data/account integration and a user-confirmed order workflow. Do not enable live orders in this phase.

## Running and stopping the daily schedule

- Install or reload: `./scripts/install_daily_paper_agent.sh`
- Remove the schedule: `./scripts/uninstall_daily_paper_agent.sh`
- Logs: `data/logs/daily-paper.out.log` and `data/logs/daily-paper.err.log`
- The local Mac user session must be active and the machine available for the weekday run. A missed scan is not backfilled as a guessed trade.

## Current blockers and completion criteria

The six-month exploratory bundle and result exist, but they are not a five-year validation and the 12-trade sample cannot establish a reliable success rate. Historical work is complete only after the five-year bundle and replay pass all integrity checks. Forward automation is set up, but the month-long review still requires a month of actual completed NSE sessions after activation; it cannot be manufactured retroactively from today's scan.
