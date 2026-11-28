# Strategy Failure Analysis

**Baseline:** frozen six-month replay, 26 May–26 November 2026
**Run:** data/backtest/experiments/strategy_intelligence_20261127_234447/diagnostics.json
**Sample:** 12 historical trades; descriptive only, not a causal analysis.

## Baseline context

The unchanged baseline produced 7 winners and 5 net losers, a 58.33% win rate with a 95% Wilson interval of 31.95%–80.67%. Net result was +1.31% versus +9.04% Nifty 50 TRI; profit factor was 2.69 and maximum drawdown was 1.13%. The historical sample is too small to infer reliable strategy behavior.

## Trade path and exit observations

- Exit reasons: 9 time exits, 1 stop exit, 2 end-of-test marks. End-of-test rows are censored observations, not completed exit decisions.
- Mean maximum favourable excursion (MFE): **0.774R**; mean maximum adverse excursion (MAE): **−0.351R**. Excursions use OHLC bars from entry through recorded exit on the backtest price basis.
- 4 of 12 trades reached +1R; none reached +2R; 1 trade touched its stop.
- Intraday order within a daily candle is unknown. Same-bar threshold conflicts are marked ambiguous and the baseline's conservative stop-first convention is retained.
- The saved baseline remains the authority for net P&L; this diagnostic does not recompute or replace the original outputs.

## Multi-label observations among five net losses

| Descriptive tag | Trades |
| --- | ---: |
| Time exit with net loss | 3 |
| MFE below +1R | 5 |
| MAE reached at least −0.5R | 2 |
| Bearish Nifty regime at signal | 3 |
| Stop exit | 1 |
| Contraction volume was not below its pre-contraction baseline | 1 |

Tags overlap. They describe co-occurring measurements and are **not causes**. Three losses with MFE below +1R had no 1R follow-through; this does not by itself justify changing the time exit. No loss tag is forced when features do not support one.

## Market regime and relative strength

| Signal-time Nifty regime | Trades | Winners |
| --- | ---: | ---: |
| Bearish | 6 | 3 |
| Neutral | 6 | 4 |

This split has very low counts and was not used to filter or size trades. The diagnostic RS percentile is an internal cross-sectional percentile of the legacy weighted excess-return score among the dated, eligible EQ universe. It is not a Minervini/vendor RS rating. Dated sector classifications were not supplied, so sector-relative analysis is unavailable.

## Limitations

- Twelve trades do not support robust failure attribution or threshold selection.
- This six-month sample has already been inspected; it is not untouched out-of-sample data.
- No closed forward-paper trades exist yet (one recorded session, zero eligible setups).
- MFE/MAE is based on daily OHLC and cannot establish intraday order of touches.
- Historical breadth is limited to the sourced point-in-time Nifty 500 EQ bundle dates (2025–2026).
