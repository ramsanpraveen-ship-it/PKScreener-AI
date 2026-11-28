# Order and Portfolio State Machine

## Current implementation

The project tracks simulated forward-paper trades with states such as `PENDING_APPROVAL`, `QUEUED`, `OPEN`, `CLOSED`, and `CANCELLED`. These are not broker orders. The existing paper session uses a unique session date and is now advanced inside a SQLite `BEGIN IMMEDIATE` transaction after freshness validation.

## Future broker lifecycle (design only)

`DRAFT → PENDING_APPROVAL → APPROVED → SUBMITTING → OPEN / PARTIALLY_FILLED / FILLED / REJECTED / UNKNOWN`

Cancellation path: `OPEN or PARTIALLY_FILLED → CANCEL_PENDING → CANCELLED / PARTIALLY_FILLED / FILLED / UNKNOWN`.

`UNKNOWN` or any local/broker discrepancy transitions to `RECONCILIATION_REQUIRED`; new entries remain frozen until a human resolves and records the discrepancy. Never transition to `FILLED` from request acceptance alone; require broker-confirmed execution quantity.

## Required durable fields

Internal order ID, broker order ID, client idempotency key, signal ID, account identity reference, user confirmation and timestamp, requested/executed price, requested/filled quantity, fees, slippage, rejection detail, source timestamps, and append-only state transition history.

## Transaction and retry rules

- Persist preview and idempotency key before submission.
- Serialize state transitions and enforce legal edges.
- A timed-out submission becomes `UNKNOWN`; query broker state before retry.
- Reconcile orders, executions, positions, and funds after every uncertain result.
- Preserve raw discrepancy metadata securely and freeze new entries on mismatch.
- Test concurrent requests, partial fills, late events, duplicate callbacks, and recovery against a mock only.

No real broker lifecycle is implemented or tested in the current repository.
