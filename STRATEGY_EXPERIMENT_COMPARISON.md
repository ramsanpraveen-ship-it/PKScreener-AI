# Strategy Experiment Comparison

**Decision:** no strategy improvement has passed validation. Live and broker behavior are unchanged.

## Comparison status

| Experiment | Status | Result |
| --- | --- | --- |
| Frozen current VCP breakout baseline | Reference only | 12-trade exploratory results preserved in data/backtest/results/ and fingerprinted in STRATEGY_BASELINE_SNAPSHOT.json. |
| VCP feature measurements: depth, higher lows, ATR/range, duration, volume, pivot distance, 52-week-high distance | Implemented and unit-tested; non-gating | Descriptive feature records generated for baseline trades. No thresholds were fitted or promoted to filters. |
| Market regime and eligible-universe breadth | Implemented and unit-tested; descriptive only | Computed as of each saved signal date using 50/200-day Nifty averages, slope, and point-in-time EQ breadth. Six bearish and six neutral observations; not enough for regime-based decisions. |
| 3/6/12-month relative returns and cross-sectional rank | Implemented and unit-tested; descriptive only | Rank uses the legacy weighted excess-return score within the supplied date-specific eligible universe. No new RS threshold or sector data was used. |
| Breakout context (volume, candle position, ATR contraction, duration, extension, gap, resistance, liquidity) | Implemented and unit-tested; descriptive only | Signal-time gap is measurable; next-session gap is unknown at signal close. No sector series was available. |
| Breakout retest entry | **Not run** | Requires an untouched chronological evaluation set and a prespecified retest definition. |
| Post-breakout consolidation entry | **Not run** | Requires an untouched chronological evaluation set and a prespecified consolidation definition. |
| ATR trail, moving-average trail, partial-profit exit | **Not run** | No rule variants were selected or tuned on the already-inspected sample. |
| Fixed 2R / time / stop baseline exit | Reference only | Existing baseline model; not an independent alternative-entry/exit comparison. |
| One-feature ablation and combinations | **Not run** | New measurements do not alter baseline gates, so ablation would be behaviorally identical. No feature was added as a filter. |
| Five-year rolling 60/20/20 walk-forward | **Blocked** | The local point-in-time bundle covers April 2025–November 2026, not five years plus warm-up. The Kaggle archive is not suitable due missing dated constituents, benchmark TRI, data gaps, and an end date in June 2026. |

## Baseline vs validation

The preserved baseline has 12 trades, 58.33% win rate (95% Wilson interval 31.95%–80.67%), +1.31% net return, 2.69 profit factor, ₹108.85 expectancy/trade, −1.13% maximum drawdown, and +9.04% Nifty 50 TRI over the six-month period. These are historical baseline metrics, not evidence that a new feature improved the strategy.

The diagnostics report is STRATEGY_FAILURE_ANALYSIS.md. Per-trade measurements are in the ignored local experiment artifact under data/backtest/experiments/strategy_intelligence_20261127_234447/.

## Passed and failed ideas

- **Passed engineering checks:** deterministic point-in-time feature calculations and their synthetic unit tests; the baseline artifact hash guard; descriptive excursion and multi-label reporting.
- **Passed strategy validation:** none.
- **Failed strategy validation:** none; proposed strategy alternatives were not run against an untouched out-of-sample period.
- **Unvalidated:** every proposed rule change, entry variant, exit variant, regime filter, and feature threshold.

Do not call the strategy improved until a prespecified, data-complete, chronological out-of-sample experiment shows better net expectancy and acceptable drawdown/benchmark-relative performance without leakage.
