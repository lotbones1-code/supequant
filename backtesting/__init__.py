"""
Backtesting Module
Professional-grade backtesting system for validating trading strategies

Components:
- HistoricalDataLoader: Fetch and cache historical market data
- BacktestEngine: Replay trades through strategies and filters
- PerformanceMetrics: Calculate comprehensive performance statistics
- ReportGenerator: Generate reports in multiple formats

Usage:
    from backtesting import HistoricalDataLoader, BacktestEngine

    # Load data
    loader = HistoricalDataLoader()
    sol_data = loader.load_data('SOL-USDT-SWAP', '2024-01-01', '2024-03-31')

    # Run backtest
    engine = BacktestEngine(initial_capital=10000)
    results = engine.run(sol_data, btc_data, '2024-01-01', '2024-03-31')

Or use the convenience script:
    python run_backtest.py --start 2024-01-01 --end 2024-03-31
"""

from .historical_data_loader import HistoricalDataLoader
from .backtest_engine import BacktestEngine, BacktestTrade
from .performance_metrics import PerformanceMetrics
from .report_generator import ReportGenerator

__all__ = [
    'HistoricalDataLoader',
    'BacktestEngine',
    'BacktestTrade',
    'PerformanceMetrics',
    'ReportGenerator'
]
