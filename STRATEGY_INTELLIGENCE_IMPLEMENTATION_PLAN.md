# Strategy Intelligence Implementation Plan

**Prepared:** 27 November 2026
**Status:** Engineering implementation complete for Stages 1–3 and dashboard/report work in Stage 5; strategy validation and Stage 4 experiments are blocked by insufficient untouched historical data.
**Safety:** Research and paper only. Do not change broker permissions, live-order gates, capital limits, or the baseline strategy's signal gates.

## Repository audit summary

The current strategy is a deterministic Minervini-inspired trend/VCP breakout screen. `technical_engine.py` composes trend, RS, contraction, breakout, and entry/exit modules; `stock_screener.py` reports candidates; `backtest_engine.py` re-evaluates the same gates as-of each signal close and simulates next-session entries. Forward paper trades are journaled separately in SQLite. The dashboard shows baseline historical metrics and the paper journal. There is no existing feature-ablation or trade-excursion report.

### Frozen baseline configuration

| Component | Current baseline behavior |
| --- | --- |
| Trend | 50/150/200-day SMA template; 20-session 200-day SMA slope; 252-session high/low template |
| VCP | Latest three confirmed high-to-low contractions must strictly decrease in depth; 180-candle analysis window |
| Contraction volume | Per-contraction mean compared with the preceding 20-session mean; aggregate dry-up is calculated, but it is **not** a main qualification gate |
| Breakout | Highest confirmed swing high in prior 60 sessions; 0.10% breakout buffer; fresh close cross; volume ≥1.5× preceding 20-session average; close in top 30% of candle; extension ≤5% |
| Relative strength | Weighted stock-minus-Nifty price return over 63/126/189/252 sessions with 0.40/0.20/0.20/0.20 weights; pass requires positive weighted value, at least two outperforming horizons, and a rising 20-session RS line. This is not an RS percentile rank. |
| Entry/exit | Structural stop, fixed 2R target, next-session open entry, adverse slippage, stop-first if stop and target touch on one bar, 20-session time exit |
| Risk | ₹100,000 initial equity; ₹60,000 deployment cap; ₹500 risk/trade; ₹20,000 position cap; three positions; existing aggregate risk cap retained |
| Backtest eligibility | Point-in-time membership, daily EQ bars with dividends, warm-up, and Nifty 50 TRI required; cash-EQ price >₹100 and 20-session average traded value >₹5 crore |

### Baseline evidence to preserve

The existing `data/backtest/results/backtest_*` files are the comparison baseline and must not be overwritten. The saved run covers 26 May–26 November 2026: **12 trades**, 7 winners, 5 losers, **58.33%** win rate (95% Wilson interval 31.95%–80.67%), +1.31% net portfolio return, +2.69 profit factor, ₹108.85 net expectancy/trade, 1.92 average win/loss, −1.13% maximum drawdown, versus +9.04% Nifty 50 TRI. This is a low-count exploratory sample, not a strategy estimate.

The bundle manifest covers 1 April 2025–26 November 2026, with performance beginning 26 May 2026. It does not contain the five years plus warm-up needed for the requested walk-forward study. The separately downloaded Kaggle version 2 archive ends in June 2026 and lacks dated membership/benchmark TRI, so it is not a valid replacement; see [KAGGLE_DATASET_ASSESSMENT.md](KAGGLE_DATASET_ASSESSMENT.md).

### Findings and gaps

1. **VCP quality is under-measured.** The current gate checks only strictly decreasing depths for the most recent three contractions. It calculates volume ratios but omits them from qualification. Higher lows, range/ATR contraction, base maturity, pivot proximity, and proximity to a meaningful 52-week high are not exposed as a single non-gating feature record.
2. **Breakout features are partial.** Relative volume, close position, and extension exist. ATR compression, base duration, gap-risk measurements, overhead resistance, liquidity-at-entry diagnostics, and sector confirmation are absent.
3. **RS is time-series only.** Four horizon excess returns and RS-line slope exist, but there is no 3/6/12-month feature record, point-in-time cross-sectional percentile, or reliable historical sector-relative measure. Keep the current weighted score label distinct from percentile ranks.
4. **No market regime/breadth series.** There is no deterministic Nifty 50 50/200-day regime classification or point-in-time universe breadth calculation.
5. **No excursion/failure journal.** Historical trade output has fills, risk, P&L and exit reason but no MFE/MAE, R-threshold path, or complete signal feature snapshot. The saved six-month sample contains 12 trades (mostly time exits); forward paper has only one recorded session and no closed-trade evidence.
6. **Entry/exit alternatives are not currently modeled.** Only confirmed breakout + next-session entry, fixed 2R, stop and time exits exist. Retest, post-breakout consolidation, ATR/MA exits, and partial exits need an isolated simulator, not changes to the baseline path.
7. **Validation is data-limited.** No accepted five-year point-in-time stock/sector/benchmark bundle is available. Do not fit or select feature thresholds, and do not treat the final 20% as available for tuning.

## Staged implementation

### Stage 1 — Freeze and fingerprint baseline

**Status: COMPLETE.** `STRATEGY_BASELINE_SNAPSHOT.json` records the configuration, key gates, metrics, and SHA-256 hashes for all four saved baseline artifacts. Tests verify the artifacts remain byte-identical.

- Add a versioned baseline configuration snapshot with module constants, gate definitions, capital limits, and current metrics.
- Record SHA-256 hashes of the four existing baseline result artifacts; preserve their paths and bytes.
- Add a guard/test that new reports use a separate experiment output directory and do not overwrite the baseline names.

### Stage 2 — Non-gating deterministic feature records

**Status: IMPLEMENTED.** Pure feature functions and as-of-date tests are in `strategy_features.py` and `market_regime.py`. Measurements are informational; the existing baseline signal gates are unchanged. Historical sector classification is unavailable and reported as such.

- Add pure Python, point-in-time-safe feature functions for VCP shape/volume/range/base/pivot context; Nifty regime and breadth; 3/6/12-month excess RS, RS-line trend and percentile; and breakout/candle/ATR/gap/overhead/liquidity context.
- Return measurement values plus observation counts, as-of date and missing-data reasons. Do not add thresholds to the baseline qualification gate.
- Add tests using synthetic indexed data, including as-of truncation tests proving future rows cannot affect an earlier record.
- Add feature explanations to scanner/dashboard without re-labeling the legacy score as an RS percentile.

### Stage 3 — Baseline trade diagnostics

**Status: COMPLETE AS DESCRIPTIVE DIAGNOSTICS.** The 12 saved trades have feature snapshots, regime context, MFE/MAE, threshold touches, and overlapping loss tags in `data/backtest/experiments/`. The output is a seen, low-count sample, not validation. The forward paper journal has no closed-trade sample.

- Enrich a separate trade-diagnostics output with signal features, regime, entry/exit, MFE/MAE, 1R/2R/stop ordering, costs, net P&L, and transparent multi-label loss categories.
- Use the existing 12 saved trades and source bars only as descriptive exploratory evidence; do not refit thresholds or revise baseline.
- Record that the one-session forward paper journal has no closed trades, so a forward failure analysis is unavailable.

### Stage 4 — Isolated experiment framework

**Status: BLOCKED.** Alternative entry/exit scenarios and walk-forward comparisons were not run because the available bundle lacks five years of point-in-time history and the current six-month sample has already been inspected. `STRATEGY_EXPERIMENT_COMPARISON.md` records the blocked scenarios. No experiment was selected or presented as an improvement.

- Add independent scenario functions for breakout retest, post-breakout consolidation, ATR trail, moving-average trail, time exit, and partial-profit exit.
- Reuse the exact baseline universe, dates, bars, fill timing, costs, slippage, position caps, and risk controls. Preserve the baseline runner unchanged.
- Write each experiment to a unique, configuration-hashed directory with one-feature-at-a-time comparisons first.
- Run only when data supports the required chronological development/validation/untouched-test partitions. Otherwise emit `BLOCKED_INSUFFICIENT_DATA` with exact missing sources; do not publish a fabricated comparison.

### Stage 5 — Reports, dashboard and final gate

**STATUS: IMPLEMENTED WITH VALIDATION GATE BLOCKED.** The read-only strategy intelligence endpoint and dashboard panel expose baseline diagnostics and evidence limits. See `STRATEGY_FAILURE_ANALYSIS.md` and `STRATEGY_EXPERIMENT_COMPARISON.md`. A validated strategy improvement remains unavailable.

- Add a strategy-intelligence report with feature definitions, baseline fingerprint, sample counts, exit/failure summaries, experiment status, intervals, and evidence limitations.
- Add dashboard panels that clearly mark baseline vs exploratory feature diagnostics and keep backtest, paper, and broker performance separate.
- State which ideas passed, failed, or remain untested. A feature is not an improvement until a prespecified chronological out-of-sample comparison supports it.

## Acceptance criteria

- Existing baseline files remain byte-identical and baseline entries/exits/risk caps are unchanged.
- Every new feature is deterministic, unit-tested, missing-data-aware, and as-of-date safe.
- No feature becomes a hard filter without a separate documented and validated experiment.
- No “win-rate improvement” is claimed from the 12-trade sample.
- Five-year/walk-forward result is withheld until complete sourced data, warm-up, point-in-time constituents, dividends, benchmark TRI, and untouched chronological OOS coverage exist.
- No real broker call or live-order permission is added.
