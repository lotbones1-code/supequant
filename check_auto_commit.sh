#!/bin/bash
# Check if auto-commit is running

SCRIPT_DIR="/Users/shamil/supequant"
PID_FILE="$SCRIPT_DIR/auto_commit.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "❌ Auto-commit is NOT running"
    echo "   Start it with: ./start_auto_commit.sh"
    exit 1
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo "✅ Auto-commit is running (PID: $PID)"
    echo ""
    echo "📊 Recent activity:"
    if [ -f "$SCRIPT_DIR/logs/auto_commit.log" ]; then
        tail -10 "$SCRIPT_DIR/logs/auto_commit.log"
    else
        echo "   No log entries yet (will appear after first commit)"
    fi
else
    echo "❌ Auto-commit process not found (PID file exists but process is dead)"
    echo "   Cleaning up PID file..."
    rm "$PID_FILE"
    echo "   Start it with: ./start_auto_commit.sh"
fi
