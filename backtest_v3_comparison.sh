#!/bin/bash
echo "🔄 BACKTEST V3 STRATEGY"
echo "====================================="
python3 run_backtest.py --start 2025-12-15 --end 2026-01-14
echo "✅ Backtest complete. Check reports in backtesting/reports/"
