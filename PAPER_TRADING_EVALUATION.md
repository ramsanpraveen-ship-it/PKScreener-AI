# Paper Trading Evaluation

## Evidence available

As of the project status updated 27 November 2026, the forward simulator has recorded **one completed NSE session** and **zero eligible trades**. This is not enough evidence to assess strategy performance. No trade should be fabricated or backfilled to meet a sample target.

The separate six-month historical replay (26 May–26 November 2026) recorded 12 trades, 7 wins and 5 losses; net return +1.31%, Nifty 50 TRI +9.04%, profit factor 2.69, maximum drawdown 1.13%, expectancy ₹108.85 per trade, and win-rate 95% Wilson interval 31.95%–80.67%. It is exploratory, small-sample evidence, not forward paper performance or a profitability claim.

## Evaluation protocol

- Accumulate at least 30 calendar days of actual completed NSE sessions; prefer 30–50 completed trades when naturally generated.
- Preserve every scan, freshness decision, candidate, rejection, approval, simulated fill, exit, cost, and operational failure with timestamps and source provenance.
- Do not backfill missing sessions or create trades for statistical convenience.
- Use next-session fills, adverse slippage, realistic fees, gap handling, and conservative stop/target ordering.
- Report trade count, win rate and interval, expectancy, R multiple, profit factor, average win/loss, loss streaks, exposure, drawdown, monthly/yearly and regime breakdowns, plus Nifty 50 TRI comparison.
- Keep historical backtest, forward paper, manual portfolio records, and any eventual broker P&L separate.

## Current decision

Gate 3 is **not met**. Review after at least 30 days of honest sessions. A quiet month with few or no trades does not establish profitability; report the low evidence honestly.
