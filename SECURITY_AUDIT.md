# Security Audit

**Assessment date:** 27 November 2026
**Result:** Local research application with a single-user local-token gate; not suitable for public network exposure.

## Observed controls

- FastAPI CORS allows only `localhost:5173` and `127.0.0.1:5173`; credentials are disabled.
- The intended Uvicorn command binds to loopback.
- No broker credentials or live order adapter were found in the reviewed source paths.
- Telegram credentials are read from environment variables and delivery errors avoid printing the token.
- SQLAlchemy queries use structured expressions; paper simulation uses SQLite parameter binding.
- The `.gitignore` excludes `.env`, local databases, logs, generated scans, and most local data.
- Frontend API mutations require explicit confirmation flags for manual/simulated actions, but those flags are not authentication.
- All `/api/*` routes except health require a constant-time bearer-token check from `PKSCREENER_API_TOKEN`; all API routes, including health, reject non-loopback client addresses.
- The dashboard keeps the entered token in tab-scoped `sessionStorage`. `scripts/run_local_api.sh` creates a random token in ignored `.env` on first launch and binds Uvicorn to `127.0.0.1`.
- The local bearer token is a single shared secret; same-origin script compromise could access it while the dashboard tab is open. No public-network or multi-user threat model is claimed.

## Findings

### Resolved in this pass: unauthenticated API

The API now requires the local bearer token for data and state-changing endpoints. This is a single-user local gate, not a multi-user identity system. Keep the API local; any proxy or network exposure requires a separate review.

### Resolved in this pass: network binding is a launch convention

The ASGI middleware rejects non-loopback peers, including health requests. Add deployment-specific tests before changing this boundary.

### Medium: numeric boundary validation

Manual-position and manual-close prices previously lacked finite-number validation. Pydantic schemas now reject NaN/infinity for these fields. Validate all numeric paths and database constraints as part of ongoing work.

### Medium: dependency vulnerability status unknown

Python `pip check` reports no broken requirements. `npm audit --omit=dev` could not reach the npm audit endpoint because DNS/network access failed; this is not a clean vulnerability audit. Re-run from a network-enabled environment.

### Medium: database startup errors are hidden from startup logs

The app records database initialization failure in application state and keeps scanner read-only availability, but the broad exception is suppressed. The health endpoint exposes a boolean; structured logs and configuration diagnostics should be added.

## Secrets and data handling

- Never commit `.env`, broker tokens, account IDs, database credentials, or local market-data files.
- Do not log raw broker responses, auth headers, session cookies, or Telegram URLs.
- Before future Kite work, use local secret storage or environment injection, redact values, and verify repository history as well as current files.
- The current app has no broker session handling, so token-expiry and account-identity behavior remain untested.

## Required before any network exposure

1. Replace the shared local token with a reviewed identity/session system before multi-user use.
2. Add proxy-specific trust-boundary tests before any reverse proxy or network exposure.
3. Add structured redacted logs, backup/restore controls, and secure file permissions.
4. Run an online dependency vulnerability audit and resolve or document findings.
5. Perform a separate security review of any proxy, TLS, firewall, or broker integration configuration.

**No security certification is implied.**
