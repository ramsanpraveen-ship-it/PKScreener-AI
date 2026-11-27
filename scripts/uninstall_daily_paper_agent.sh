#!/bin/bash
set -euo pipefail
AGENT_FILE="$HOME/Library/LaunchAgents/com.pkscreener.ai.daily-paper.plist"
launchctl bootout "gui/$(id -u)" "$AGENT_FILE" >/dev/null 2>&1 || true
rm -f "$AGENT_FILE"
echo "Daily paper scan schedule removed."
