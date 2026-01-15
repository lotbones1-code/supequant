#!/bin/bash

# Weekly Strategy Auto-Improvement Script
# Run this every Sunday to continuously improve parameters
# Usage: ./weekly_auto_improve.sh

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🚀 WEEKLY STRATEGY AUTO-IMPROVEMENT"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📅 Started: $(date)"
echo ""

# Configuration
SYMBOL="SOLUSDT"
START_DATE="2025-12-15"
END_DATE="2026-01-14"

# Step 1: Run backtest with current parameters
echo "════════════════════════════════════════════════════════════"
echo "STEP 1: 🏃 Running baseline backtest with current parameters..."
echo "════════════════════════════════════════════════════════════"
python backtest.py --symbol $SYMBOL --start-date $START_DATE --end-date $END_DATE

if [ $? -ne 0 ]; then
    echo "❌ Backtest failed"
    exit 1
fi

echo "✅ Baseline backtest complete"
echo ""

# Step 2: Analyze current trades
echo "════════════════════════════════════════════════════════════"
echo "STEP 2: 🔍 Analyzing current trades for patterns..."
echo "════════════════════════════════════════════════════════════"
python -c "from backtesting.trades_analyzer import TradesAnalyzer; analyzer = TradesAnalyzer(); analyzer.run_full_analysis()"

if [ $? -ne 0 ]; then
    echo "❌ Trade analysis failed"
    exit 1
fi

echo "✅ Trade analysis complete"
echo ""

# Step 3: Run parameter optimization
echo "════════════════════════════════════════════════════════════"
echo "STEP 3: 🧪 Testing parameter variations..."
echo "════════════════════════════════════════════════════════════"
python -c "from backtesting.parameter_optimizer import ParameterOptimizer; optimizer = ParameterOptimizer(); optimizer.run_optimization(max_tests=20)"

if [ $? -ne 0 ]; then
    echo "❌ Parameter optimization failed"
    exit 1
fi

echo "✅ Parameter optimization complete"
echo ""

# Step 4: Summary
echo "════════════════════════════════════════════════════════════"
echo "📊 WEEKLY IMPROVEMENT SUMMARY"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📁 Reports generated:"
ls -lh backtesting/reports/ | tail -5
echo ""
echo "📁 Analysis files:"
ls -lh backtesting/*.json 2>/dev/null | tail -3
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Weekly auto-improvement complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next steps:"
echo "  1. Review: backtesting/trades_analysis.json (patterns found)"
echo "  2. Review: backtesting/optimization_results.json (best params)"
echo "  3. If parameters improved: git add + commit + deploy"
echo "  4. If not: keep current parameters, run again next week"
echo ""
echo "⏰ Finished: $(date)"
echo ""
