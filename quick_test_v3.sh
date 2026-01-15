#!/bin/bash

# QUICK V3 SUCCESS RATE TEST
# Runs in 5 minutes - shows if strategy is actually working
# Usage: ./quick_test_v3.sh

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         🚀 QUICK V3 SUCCESS RATE TEST - 5 MIN                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "⏱️  Test started: $(date)"
echo ""

# Configuration
SYMBOL="SOLUSDT"
START_DATE="2026-01-07"  # Last 7 days only (fast test)
END_DATE="2026-01-14"

echo "📊 Testing V3 Strategy on: $SYMBOL"
echo "📅 Period: $START_DATE to $END_DATE"
echo "⚙️  Running backtest with V3 parameters..."
echo ""

# Run quick backtest
python backtest.py \
  --symbol $SYMBOL \
  --start-date $START_DATE \
  --end-date $END_DATE \
  --output quick_test_result.json

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ BACKTEST FAILED"
    echo ""
    echo "Troubleshooting:"
    echo "1. Check if backtest.py exists: ls -la backtest.py"
    echo "2. Check Python installed: python --version"
    echo "3. Check dependencies: pip list | grep -E 'pandas|ta'"
    exit 1
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    📈 RESULTS                                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Parse results
if [ -f "quick_test_result.json" ]; then
    echo "Extracting key metrics..."
    echo ""
    
    python3 << 'EOF'
import json
import sys

try:
    with open('quick_test_result.json', 'r') as f:
        results = json.load(f)
    
    # Extract metrics
    total_trades = results.get('total_trades', 0)
    winning_trades = results.get('winning_trades', 0)
    losing_trades = results.get('losing_trades', 0)
    win_rate = results.get('win_rate', 0)
    total_return = results.get('total_return', 0)
    profit_factor = results.get('profit_factor', 0)
    avg_win = results.get('avg_win', 0)
    avg_loss = results.get('avg_loss', 0)
    max_drawdown = results.get('max_drawdown', 0)
    
    # Display results
    print(f"Total Trades:        {total_trades}")
    print(f"Winning Trades:      {winning_trades}")
    print(f"Losing Trades:       {losing_trades}")
    print("")
    print(f"🎯 Win Rate:         {win_rate:.1f}%")
    print(f"📊 Total Return:     {total_return:+.2f}%")
    print(f"💰 Profit Factor:    {profit_factor:.2f}x")
    print(f"💹 Avg Win:          {avg_win:+.2f}%")
    print(f"📉 Avg Loss:         {avg_loss:+.2f}%")
    print(f"⚠️  Max Drawdown:     {max_drawdown:.2f}%")
    print("")
    
    # Verdict
    print("╔════════════════════════════════════════════════════════════════╗")
    if win_rate >= 50 and profit_factor >= 1.2:
        print("║  ✅ GOOD - Strategy is working! Ready to deploy or refine     ║")
    elif win_rate >= 45 and profit_factor >= 1.0:
        print("║  🟡 OKAY - Working but needs tuning. Run weekly optimizer    ║")
    else:
        print("║  ❌ BAD - Not working. Debug or reload V2                     ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print("")
    
except Exception as e:
    print(f"Error parsing results: {e}")
    sys.exit(1)
EOF
    
else
    echo "⚠️  Results file not found. Backtest may have failed."
fi

echo ""
echo "⏱️  Test finished: $(date)"
echo ""
echo "🔥 NEXT STEPS:"
echo "  ✅ If win rate > 50%:     Deploy to paper trade or go live"
echo "  🟡 If win rate 45-50%:    Run weekly optimizer to tune parameters"
echo "  ❌ If win rate < 45%:     Revert to V2 or debug"
echo ""
echo "📊 View full results:"
echo "   cat quick_test_result.json | python -m json.tool"
echo ""
echo "📈 Or run full analysis:"
echo "   python -c \"from backtesting.trades_analyzer import TradesAnalyzer; TradesAnalyzer().run_full_analysis()\""
echo ""
