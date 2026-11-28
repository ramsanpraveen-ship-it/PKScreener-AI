# Local Deployment Guide

## Intended use

Local research and simulated paper trading only. Do not expose the API to a LAN or public network. There is no live broker execution capability.

## Prerequisites

- macOS or compatible Python environment matching the pinned `requirements.txt`.
- Node.js/npm matching `frontend/package-lock.json`.
- PostgreSQL only for optional dashboard watchlist/manual portfolio features; forward paper history is SQLite.
- Optional local Ollama for explanations; never required for deterministic risk calculations.

## Setup

1. Create/activate the repository Python virtual environment and install `requirements.txt`.
2. Install frontend dependencies with `npm ci` from `frontend/`.
3. Configure PostgreSQL locally only if using database-backed dashboard panels. Keep connection strings in ignored `.env`/environment configuration.
4. Start the API with `scripts/run_local_api.sh`. On first run it creates a random token in ignored `.env` with owner-only file permissions, then binds Uvicorn to `127.0.0.1:8000` to match the Vite proxy. Enter the local token in the dashboard; the browser keeps it only for that tab session. Start the frontend development server on localhost. Verify `/api/health` reports `local_only=true` and `orders_enabled=false`.
5. Run the screener only after verifying expected NSE session/calendar and market-data freshness. The forward paper processor requires the scan metadata sidecar; missing or mismatched metadata blocks advancement.

## Operations

- Review API health and scan freshness before interpreting results.
- Back up `data/forward_paper.sqlite3` when the simulator is stopped; protect backups as local account research data.
- Do not commit `.env`, databases, scans, cache, or broker credentials.
- Update/verify NSE holidays and special sessions from official notices before each calendar year; 2027 coverage is currently pending.
- Review [INCIDENT_RECOVERY_GUIDE.md](INCIDENT_RECOVERY_GUIDE.md) before operating scheduled scans.
- The Kaggle dataset named by the project owner is downloaded into ignored local storage and assessed in [KAGGLE_DATASET_ASSESSMENT.md](KAGGLE_DATASET_ASSESSMENT.md); it is not accepted as backtest evidence yet.

## Verification commands

```sh
.venv/bin/python -m unittest discover -v
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m pip check
cd frontend && npm run build
cd frontend && npm audit --omit=dev
```

The npm audit requires network access. Passing commands do not establish strategy profitability, security certification, broker behavior, or production readiness.
