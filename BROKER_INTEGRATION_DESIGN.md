# Broker Integration Design

## Current state

No Kite Connect adapter, authentication flow, broker account reader, order simulator, reconciliation process, or live order endpoint is present. Live orders remain disabled. This document specifies a future staged design only; it does not authorize or implement broker access.

## Adapter boundary

Strategy and risk code must depend on an application-owned interface, not Kite SDK calls:

- `authenticate()` / `session_status()`
- `account_identity()` / `available_funds()`
- `holdings()` / `positions()` / `orders()` / `order_history()` / `executions()`
- `quote()` / `instrument_master()`
- `place_order()` / `modify_order()` / `cancel_order()`
- `reconcile()`

Use separate implementations for a deterministic mock and a future Kite read-only adapter. Keep exchange/product/variety and tick-size validation in a tested boundary layer. Store no credentials in source or logs.

## Stages

1. **Read-only:** authenticate, verify account identity, read funds/holdings/positions/orders, redact sensitive output, handle expiry/rate limits, and prove no mutation methods can be called.
2. **Mock execution:** simulate acknowledgements, rejection, partial fill, delayed update, timeout, duplicate request, cancellation, price gaps, and insufficient funds. On timeout, reconcile before any retry.
3. **Live eligibility design:** only after all readiness gates pass, prepare a per-order preview and require individual confirmation. Server must independently revalidate freshness, account, instrument, price, funds, aggregate risk, session, duplicate/conflicting orders, kill switch, and reconciliation status. A global mode toggle cannot authorize future orders.

## Prohibitions

Do not scrape broker login, bypass authentication, store tokens in Git, blindly retry ambiguous order submission, mark an order filled on HTTP success alone, or enable unattended execution. No implementation in this release may submit a real order.
