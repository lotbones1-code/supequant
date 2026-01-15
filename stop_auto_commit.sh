#!/bin/bash
# Stop the auto-commit script

SCRIPT_DIR="/Users/shamil/supequant"
PID_FILE="$SCRIPT_DIR/auto_commit.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  Auto-commit is not running (no PID file found)"
    exit 1
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    kill "$PID"
    rm "$PID_FILE"
    echo "✅ Auto-commit stopped (PID: $PID)"
else
    echo "⚠️  Process not found (may have already stopped)"
    rm "$PID_FILE"
fi
