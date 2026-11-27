# Phase 7: local dashboard

The dashboard is a React + TypeScript + MUI app backed by a loopback FastAPI
service. The manual portfolio uses PostgreSQL; the automated forward paper book
uses a local SQLite journal so it remains available independently of PostgreSQL.
There is no Kite integration or real order-placement route.

## Safety behavior

- Candidate data is shown only when the newest scan metadata proves that the
  benchmark and every stock row match the expected NSE session.
- A newer stale or partial run hides all candidate rows; the API never falls
  back to an older apparently fresh scan.
- Portfolio mark prices and unrealized P&L are shown only from a fresh scan.
- Python supplies the displayed risk limits. The dashboard does not calculate
  trade size or submit orders.
- PostgreSQL downtime leaves the freshness display available while watchlist
  and portfolio editing are disabled.

## Local setup

1. Create a local PostgreSQL database named `pkscreener_ai`, and set
   `DATABASE_URL`, for example:

   ```sh
   export DATABASE_URL='postgresql+psycopg://localhost/pkscreener_ai'
   ```

2. Install the API dependencies and start the API from the project root:

   ```sh
   .venv/bin/pip install -r backend/requirements.txt
   .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```

3. In a second terminal, install and start the dashboard:

   ```sh
   cd frontend
   npm install
   npm run dev
   ```

The frontend is served at `http://127.0.0.1:5173`; API requests are proxied to
`127.0.0.1:8000`. Bind addresses are local-only by default.

## API routes

- `GET /api/health` — local API, database, and scan status.
- `GET /api/dashboard` — freshness status, risk limits, watchlist, and positions.
- `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/{symbol}`.
- `GET /api/portfolio`, `POST /api/portfolio`,
  `POST /api/portfolio/{id}/close` for manually recorded positions.
- `GET /api/forward-paper` — daily simulated positions, pending setups, scorecard, and history.
- `PUT /api/forward-paper/mode` — `manual`, `ask`, or `auto`; all modes control simulation only.
- `POST /api/forward-paper/{id}/approve` — confirm a pending setup for next-session simulated entry.
- `GET /api/paper-trades`, `POST /api/paper-trades`,
  `POST /api/paper-trades/{id}/close` for the older manual simulation journal.

Paper-trade limits use the deterministic Python risk configuration. The
journal reports realized P&L, win rate, and profit factor before costs; it does
not claim a validated strategy result or send orders. Historical evaluation
still requires the separate, provenance-checked backtest data bundle.

Telegram alerts are off unless `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are
set in the local API process environment. The dashboard sends only after a
manual confirmation and only when a fresh validated scan has candidates. The
alert sends candidate symbols/statuses and the scan date to Telegram, so using
this optional feature transmits those details outside the device. Never place
the bot token in source files or commit it. No alert is sent by default.


## Forward paper tracking

The installed LaunchAgent runs the full qualified-universe scan at 17:30 local
time on weekdays. A session is recorded only when all stock rows and the
benchmark pass the NSE freshness gate. Install/reload it with
`./scripts/install_daily_paper_agent.sh`; remove it with
`./scripts/uninstall_daily_paper_agent.sh`. Logs are written under
`data/logs/`. The Mac user session must be active and the machine available.

`manual` waits for a click before each simulated next-session entry. `ask`
automatically queues deterministic rule scores of at least 90% and waits for
confirmation below 90%. `auto` queues every eligible setup for simulated
next-session execution. The displayed score is not a probability estimate.
The paper journal is `data/forward_paper.sqlite3`. P&L estimates statutory
charges and 5 bps per-side slippage, assumes zero broker brokerage, and excludes
dividend cash actions.
