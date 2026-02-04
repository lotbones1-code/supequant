#!/bin/bash
# Quick status check for the trading system

echo "═══════════════════════════════════════════════════════"
echo "         ELITE QUANT TRADING SYSTEM STATUS"
echo "═══════════════════════════════════════════════════════"
echo ""

# Check if bot is running
BOT_PID=$(pgrep -f "python.*main.py" | head -1)
if [ -n "$BOT_PID" ]; then
    echo "🤖 Bot: RUNNING (PID $BOT_PID)"
else
    echo "🤖 Bot: ❌ NOT RUNNING"
fi

# Get latest cycle info from logs
echo ""
echo "📊 Latest Log Output:"
echo "---"
tail -15 /Users/shamil/supequant/logs/nohup.out 2>/dev/null | grep -E "(CYCLE|paused|Position|Entry|TP|SL|drawdown|ERROR)" | tail -5
echo "---"

# Check Hyperliquid position
echo ""
echo "💰 Live Position (Hyperliquid):"
cd /Users/shamil/supequant
.venv/bin/python -c "
from data_feed.hyperliquid_client import HyperliquidClient
client = HyperliquidClient()
positions = client.get_positions()
if positions:
    for p in positions:
        side = 'LONG' if float(p['pos']) > 0 else 'SHORT'
        size = abs(float(p['pos']))
        entry = float(p['avgPx'])
        pnl = float(p['upl'])
        pnl_emoji = '🟢' if pnl >= 0 else '🔴'
        print(f'   {side} {size} SOL @ \${entry:.2f}')
        print(f'   {pnl_emoji} Unrealized PnL: \${pnl:.2f}')
else:
    print('   No open positions')
" 2>/dev/null

echo ""
echo "═══════════════════════════════════════════════════════"
