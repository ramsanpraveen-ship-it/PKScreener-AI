#!/bin/bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
AGENT_FILE="$AGENT_DIR/com.pkscreener.ai.daily-paper.plist"
mkdir -p "$AGENT_DIR" "$PROJECT_DIR/data/logs"
PROJECT_DIR="$PROJECT_DIR" python3 - "$PROJECT_DIR/launchd/com.pkscreener.ai.daily-paper.plist" "$AGENT_FILE" <<'PY'
import os
import sys
from xml.sax.saxutils import escape
from pathlib import Path

template = Path(sys.argv[1]).read_text(encoding="utf-8")
Path(sys.argv[2]).write_text(
    template.replace("@PROJECT_DIR@", escape(os.environ["PROJECT_DIR"])),
    encoding="utf-8",
)
PY
launchctl bootout "gui/$(id -u)" "$AGENT_FILE" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$AGENT_FILE"
launchctl enable "gui/$(id -u)/com.pkscreener.ai.daily-paper"
echo "Daily paper scan scheduled for weekdays at 17:30 local time."
