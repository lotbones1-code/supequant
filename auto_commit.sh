#!/bin/bash
# Auto-commit script - commits and pushes changes every minute
# This keeps GitHub in sync with local changes automatically

REPO_DIR="/Users/shamil/supequant"
LOG_FILE="$REPO_DIR/logs/auto_commit.log"

# Create logs directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Change to repo directory
cd "$REPO_DIR" || exit 1

log "🚀 Auto-commit script started"

# Main loop - runs every minute
while true; do
    # Check if there are any changes (staged, unstaged, or untracked)
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard)" ]; then
        log "📝 Changes detected, committing..."
        
        # Add all changes
        git add -A
        
        # Create commit with timestamp
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        COMMIT_MSG="Auto-commit: $TIMESTAMP"
        
        # Commit (allow empty in case nothing actually changed after staging)
        if git commit -m "$COMMIT_MSG" --allow-empty 2>>"$LOG_FILE"; then
            log "✅ Committed: $COMMIT_MSG"
            
            # Push to GitHub
            if git push origin main 2>>"$LOG_FILE"; then
                log "🚀 Pushed to GitHub successfully"
            else
                log "⚠️  Push failed (check log for details)"
            fi
        else
            log "⚠️  Commit failed (check log for details)"
        fi
    else
        log "✓ No changes detected"
    fi
    
    # Wait 60 seconds before next check
    sleep 60
done
