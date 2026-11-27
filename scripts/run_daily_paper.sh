#!/bin/bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
cd "$PROJECT_DIR"
# Serialize scheduled/manual runs so a session is scanned only once at a time.
LOCK_DIR="$PROJECT_DIR/data/logs/daily-paper.lockdir"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "A daily paper scan is already running; skipping duplicate invocation."
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
# Skip weekends, holidays, and dates not configured in the NSE calendar.
if ! "$PYTHON" - <<'PY'
from datetime import datetime
import sys
from nse_calendar import IST, get_latest_expected_nse_session
now = datetime.now(IST)
try:
    valid = get_latest_expected_nse_session(now) == now.date()
except ValueError:
    valid = False
sys.exit(0 if valid else 1)
PY
then
  echo "No configured completed NSE session today; skipping daily paper run."
  exit 0
fi
# Avoid repeating a same-session scan when manually started before the schedule.
if "$PYTHON" - <<'PY'
from datetime import datetime
from nse_calendar import IST, get_latest_expected_nse_session
from forward_paper import get_forward_book
expected = get_latest_expected_nse_session(datetime.now(IST)).isoformat()
raise SystemExit(0 if get_forward_book()["latest_session"] == expected else 1)
PY
then
  echo "Paper book already processed today's NSE session; skipping duplicate scan."
  exit 0
fi
"$PYTHON" -u stock_screener.py
