# Phase 5: historical backtest inputs

`backtest_engine.py` reuses the existing Python screening rules. It evaluates
each close using only candles available through that date, enters at the next
session open, sizes long cash positions under the existing ₹500 risk / ₹20,000
allocation / three-position / ₹60,000 deployment limits, and exits on stops,
2R targets, or the 20-session limit. If a candle touches both stop and target,
the stop is assumed first. A gap through a stop fills at the open with adverse
slippage.

It also reapplies the existing universe filters as of each signal date: EQ
series only, closing price above ₹100, and 20-session average traded value
above ₹5 crore. Liquidity is computed as daily close multiplied by volume.

The engine deliberately refuses a backtest unless the caller certifies that
the point-in-time constituent history is complete and sourced. Current Nifty
500 constituents are not a historical universe. Missing member-day prices,
missing dividend action data, and mismatched benchmark dates also stop the run.

## Local input bundle

Place files under `data/backtest/`:

```text
data/backtest/
  universe_manifest.json
  universe_history.csv
  nifty50_price.csv
  nifty50_tri.csv
  stocks/
    SYMBOL.csv
```

`universe_history.csv` columns:

```text
symbol,series,valid_from,valid_to,source_url
```

Intervals are inclusive. Every entry and exit must be dated from NSE Indices
official releases or archived official constituent files. `source_url` is
required on each membership interval. `universe_manifest.json` must identify
coverage dates, a source URL, and set `complete_point_in_time_history` to
`true` only after membership changes, suspensions, delistings, and symbol
changes have been reconciled.

Each `stocks/SYMBOL.csv` needs a date index plus `Open,High,Low,Close,Volume,
Dividends`. Membership rows must have `series=EQ`. Prices must be split-adjusted but not dividend-adjusted; dividend
cash is credited to positions held before the ex-date. This avoids using
future dividend adjustments in signal prices and avoids dropping cash
distributions from portfolio returns. The dataset must include at least 253
Nifty sessions (about 400 calendar days) before the requested start date for
indicator warm-up. The normal performance window must be at least five
years. For an explicitly exploratory six-month run, use `--six-month-research`;
this changes only the minimum window length and does not relax the membership,
OHLCV/dividend, warm-up, or benchmark checks. The end date must be a completed
benchmark session.

Every member-day in the performance window must have an OHLCV row. A member
must also have a complete 253-session benchmark-aligned signal window before
the engine will evaluate it. A symbol with less history is skipped until that
window exists; a missing bar inside an otherwise available warm-up window
stops the run rather than shifting indicators across non-consecutive dates.

`nifty50_price.csv` requires `Close` for the existing relative-strength
screen. `nifty50_tri.csv` requires `Total Return Index` and is the performance
benchmark. Use Nifty Indices' historical data and Total Returns Index download
for the latter; a Nifty 50 price index is not a substitute. The historical
report form currently accepts at most one year per request, so acquire a
longer window as adjacent slices and reconcile duplicate boundary dates.

## Cost model and limits

The default cost estimate includes delivery STT (10 bps on each side), buyer
stamp duty (1.5 bps), SEBI turnover fee, GST on modeled exchange/regulatory
charges, and a conservative upper-slab NSE transaction charge by effective
date. Brokerage defaults to zero because no broker was selected and is
configurable. Slippage defaults to 5 bps per side; this is an explicit
research assumption, not measured market impact. Historical fee breakpoints
are encoded in `_nse_transaction_bps` and should be revisited if the official
schedule changes.

NSE source references:

- [Investor levies, STT, stamp duty and SEBI fee](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies)
- [NSE transaction charges from April 2023](https://nsearchives.nseindia.com/content/circulars/FA56129.pdf)
- [NSE transaction charges from April 2024](https://nsearchives.nseindia.com/content/circulars/FA61137.pdf)
- [NSE uniform cash-market charges from October 2024](https://nsearchives.nseindia.com/content/circulars/FA64232.pdf)
- [NSE cash-market charges from March 2026](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf)
- [Nifty Indices historical index and TRI data](https://www.niftyindices.com/reports/historical-data)
- [Nifty 500 index and constituent methodology](https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-500)

No performance result should be presented until the 5-year window, preceding
warm-up, point-in-time universe, dividend series, and Nifty 50 TRI all pass
these checks. The report includes win rate, profit factor (net winning rupees
divided by absolute net losing rupees), and average win/loss ratio (average
net winner divided by average absolute net loser). These are different
measures and should be read alongside trade count, expectancy, total return,
and maximum drawdown. Even then, fixed slippage and fee assumptions are
estimates; backtest output is research evidence, not a promise of future
returns.

## Run

From the project root after all files are prepared:

```sh
.venv/bin/python backtest_engine.py \
  --data-dir data/backtest \
  --start-date 2021-11-26 \
  --end-date 2026-11-26
```

The example dates are a format example only. Choose a window whose end date is
present in both benchmark files and whose universe and stock files cover the
preceding warm-up. For a six-month exploratory replay, add
`--six-month-research`; the rest of the completeness guards remain active.
The command writes a metrics JSON, assumptions JSON, trade CSV, and daily
equity-curve CSV under `data/backtest/results/`.

## Preparing the exploratory six-month bundle

For the current research run, the sourced bundle was built with:

```sh
.venv/bin/python scripts/prepare_historical_backtest_bundle.py
.venv/bin/python backtest_engine.py --data-dir data/backtest \
  --start-date 2026-05-26 --end-date 2026-11-26 --six-month-research
```

The preparation script refuses to overwrite a non-empty bundle. It uses dated
NSE bhavcopies to verify cash-EQ eligibility and execution-session bars, Yahoo
Finance for split-adjusted history and corporate-action fields, and Nifty
Indices for the price and total-return benchmarks. It also reconstructs
merger-delisted JBCHEPHARM warm-up bars from NSE reports. The NSE circular
confirms a live cash-market session on Sunday, 2026-02-01; Yahoo omits that
session, so missing warm-up rows are patched from the official NSE report, with
an explicit flat, zero-volume row only where NSE has no EQ trade for that name.
This no-trade representation is documented in the bundle manifest.

The report includes a 95% Wilson interval for the observed win rate. It
quantifies sampling uncertainty for the historical trade sample only; it is
not a calibrated probability of future profitability or a strategy confidence
score. A short run with few trades should be treated as low-confidence evidence.

For windows of at least five years, the runner also emits independent
chronological 60% development / 20% validation / 20% untouched out-of-sample
results in the saved metrics JSON. Each partition starts with the configured
portfolio capital; signals are still formed only from candles through their
signal close and entries occur at the next session open. Short research windows
do not display walk-forward partitions. Metrics also include calendar-year and
monthly total-portfolio returns, gross trade P&L, average R, consecutive losses,
holding period, market exposure, average deployed capital and a zero-return
cash-only baseline. The equity curve stores daily cash, deployed capital,
unrealized P&L, open-position risk, and portfolio equity.

The checked-in local bundle currently covers 1 April 2025 through 26 November
2026 (410 benchmark sessions) and is suitable only for the saved six-month
research replay. It does not contain the five years plus warm-up needed for
validation. A complete point-in-time constituent history, OHLCV/dividends and
benchmark TRI back to at least 2020-11-26 must be assembled before claiming a
five-year result. The engine fails closed on the existing bundle for a request
that exceeds this coverage.
