# Trading Risk Specification

## Scope and boundaries

NSE cash equities, long-only swing research, no leverage, shorting, futures, or options. The AI may explain deterministic Python results but cannot set prices, stops, targets, eligibility, or quantity. All current trading workflows are paper/manual records; actual broker orders are disabled.

## Configured research account

| Control | Value | Current enforcement |
| --- | ---: | --- |
| Starting capital | ₹100,000 | sizing config |
| Maximum deployment | ₹60,000 | sizing and paper entry |
| Maximum risk per position | ₹500 | sizing and paper entry |
| Concurrent positions | 3 | sizing and paper entry |
| Maximum allocation per position | ₹20,000 | sizing and paper entry |
| Aggregate open risk | ₹1,500 | derived as 3 × ₹500; enforced in Python sizing and forward simulator |
| Holding guide | 2–20 sessions | strategy guidance; simulator time exit at 20 sessions |
| Minimum reward/risk | 2:1 intended | candidate target uses 2R reference; not a guarantee |

Aggregate open risk for sizing is calculated as the sum of each open position's quantity multiplied by entry-to-stop distance. The simulator uses a cost-adjusted per-share risk estimate for newly opened positions. This is an approximation; gaps, slippage, fees, halts, and stop execution can cause losses beyond planned risk.

## Missing controls (release blockers for live use)

Daily loss, weekly loss, portfolio drawdown, maximum order count, maximum notional, allowed price deviation, failed-attempt cap, sector concentration, pending-order exposure, available-cash reconciliation, and broker-confirmed positions are not comprehensively enforced. Their defaults are not silently invented in this release. Live entries must remain unavailable until these controls are specified, implemented, and tested.

## Fail-closed rules

- Missing/mismatched scan freshness metadata blocks paper-book advancement.
- Stale or inconsistent market data blocks candidates.
- Invalid/non-finite prices are rejected.
- Positions exceeding configured caps are rejected by Python.
- Unknown or unverified broker/account state must reject any future live order.
- Any future risk-limit breach blocks new entries and requires explicit review.

## Limitations

Risk budgets are planning constraints, not loss guarantees. Stop gaps, liquidity, exchange outages, corporate actions, model/data defects, and broker execution may cause substantially different outcomes. Never increase limits automatically, and never infer profitability from passing risk tests.
