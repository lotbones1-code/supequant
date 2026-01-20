#!/bin/bash
# Start the auto-commit script in the background

SCRIPT_DIR="/Users/shamil/supequant"
PID_FILE="$SCRIPT_DIR/auto_commit.pid"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "⚠️  Auto-commit is already running (PID: $OLD_PID)"
        echo "   Use ./stop_auto_commit.sh to stop it first"
        exit 1
    else
        # PID file exists but process is dead, remove it
        rm "$PID_FILE"
    fi
fi

# Start the script in background
cd "$SCRIPT_DIR" || exit 1
nohup bash "$SCRIPT_DIR/auto_commit.sh" > /dev/null 2>&1 &
NEW_PID=$!

# Save PID
echo $NEW_PID > "$PID_FILE"

echo "✅ Auto-commit started (PID: $NEW_PID)"
echo "   It will commit and push changes every minute"
echo "   Logs: logs/auto_commit.log"
echo "   To stop: ./stop_auto_commit.sh"
