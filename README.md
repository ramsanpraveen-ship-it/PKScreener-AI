# PKScreener-AI

Local research and paper-trading tools for NSE cash-equity swing setups. The
project combines a deterministic Python screening and risk engine with a React
dashboard and an optional local Ollama analyst. Python remains authoritative
for signals, sizing, and risk decisions; the language model only explains the
analysis.

> **Research software, not investment advice.** All trading modes simulate
> activity only. The project has no broker order integration, and live orders
> are disabled.

## What it includes

- NSE cash-equity universe filtering and daily market-data freshness checks.
- Trend-template, VCP-style contraction, relative-strength, swing, and
  breakout analysis.
- Deterministic entry, exit, and position sizing under portfolio risk limits.
- Manual, approval-based, and paper-auto forward simulation modes.
- A FastAPI service and React/TypeScript dashboard for screening, paper trades,
  and historical replay.
- A provenance-checked historical backtest engine with next-session execution,
  transaction-cost estimates, point-in-time universe validation, and
  chronological walk-forward reporting when sufficient history is provided.
- Optional local Ollama explanations. AI output cannot override Python prices,
  quantities, or risk decisions.
- A read-only strategy-intelligence panel with non-gating VCP, relative-strength,
  breakout, market-regime, MFE/MAE, and failure-tag diagnostics for the saved
  baseline sample.

## Risk and execution boundaries

The default account configuration is ₹100,000 starting capital, ₹60,000 maximum
deployment, ₹500 maximum risk per trade, three concurrent positions, and a
₹20,000 per-position cap. The backtest uses long-only NSE cash-equity positions,
next-session entries, adverse slippage, delivery-cost estimates, stop-first
handling when OHLC data cannot establish intraday ordering, and a maximum
20-session holding period.

No F&O, leverage, short selling, broker credentials, or automated broker orders
are part of this project. Forward paper automation records simulated trades
only.

## Requirements

- Python 3.10 or newer
- Node.js 20 or newer and npm
- PostgreSQL for the dashboard's manual portfolio/watchlist database
- Optional: Ollama with the model named in `Modelfile`

Create a virtual environment and install the Python dependencies:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r backend/requirements.txt
```

The database URL is read from `DATABASE_URL`. For a local PostgreSQL database:

```sh
export DATABASE_URL='postgresql+psycopg://localhost/pkscreener_ai'
```

Start the API from the project root (the script creates a local bearer token on first launch):

```sh
./scripts/run_local_api.sh
```

In a second terminal, start the dashboard:

```sh
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` and enter the token from the ignored `.env` file. The API requires the token and rejects non-loopback requests. For more
dashboard and API details, see [DASHBOARD_README.md](DASHBOARD_README.md).

## Running tests and building the dashboard

```sh
.venv/bin/python -m unittest discover -v
cd frontend && npm run build
```

## Historical backtesting

The repository contains a small **exploratory six-month replay report** from
26 May 2026 through 26 November 2026. It records 12 trades and a +1.31% net
return versus +9.04% for the Nifty 50 TRI during that interval. This is a small
sample and is not evidence of a validated or profitable strategy. Historical
report files are under `data/backtest/results/`.

Raw market data and local scan state are excluded from Git. The saved input
bundle currently covers only 1 April 2025 through 26 November 2026, which is
not enough to support a five-year walk-forward study. Do not claim five-year
validation until the point-in-time constituent history, OHLCV and dividend
actions, and benchmark TRI cover the full test window and indicator warm-up.

To run a backtest after preparing a complete bundle, follow
[BACKTEST_README.md](BACKTEST_README.md). The engine deliberately fails closed
when historical membership, daily bars, dividends, or benchmark coverage are
missing. It does not substitute today's constituents for historical members.

The strategy-intelligence diagnostics are generated separately from the saved
baseline artifacts:

```sh
.venv/bin/python tools/generate_strategy_intelligence_report.py
```

The command writes to a unique `data/backtest/experiments/` directory and
refuses to overwrite the frozen baseline. It describes the inspected 12-trade
sample only; it does not estimate a reliable win rate or select improved entry
or exit rules. Alternative-entry/exit and five-year walk-forward validation
remain blocked until sufficient untouched, provenance-checked historical data
is available. See [the implementation plan](STRATEGY_INTELLIGENCE_IMPLEMENTATION_PLAN.md),
[failure analysis](STRATEGY_FAILURE_ANALYSIS.md), and
[experiment status](STRATEGY_EXPERIMENT_COMPARISON.md).

## Local-only integrations

Telegram alerts are optional and disabled unless `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` are set in the API process environment. Never commit these
values. The daily macOS paper-scan scheduler is optional; its installer creates
a user-specific LaunchAgent from the current checkout path. See
[PAPER_EVALUATION_PLAN.md](PAPER_EVALUATION_PLAN.md) for its operating notes.

## Repository description

Suggested GitHub description: **Local NSE cash-equity research and paper-trading platform with deterministic screening, risk management, and walk-forward backtesting. No broker order execution.**
