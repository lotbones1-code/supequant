# Backtesting System Documentation

Professional-grade backtesting engine for validating the elite quant trading system.

## Overview

The backtesting system allows you to test your trading strategies against historical data to validate performance before risking real capital.

### What It Does

1. **Loads Historical Data** - Fetches OHLCV data from OKX for both SOL and BTC
2. **Replays Market Conditions** - Simulates real-time market state at each point in time
3. **Generates Trading Signals** - Runs your strategies (breakout, pullback) on historical data
4. **Validates Through Filters** - All 7 filters must pass, just like live trading
5. **Simulates Execution** - Models realistic trade execution with slippage
6. **Tracks Performance** - Calculates comprehensive metrics
7. **Generates Reports** - Creates detailed reports for analysis

## Quick Start

### Run a Backtest

```bash
# Simple 3-month backtest
python run_backtest.py --start 2024-01-01 --end 2024-03-31

# Quick 30-day test
python run_backtest.py --quick

# Named backtest with custom capital
python run_backtest.py --start 2024-01-01 --end 2024-06-30 --name q1_q2_2024 --capital 20000

# Force refresh data (ignore cache)
python run_backtest.py --start 2024-01-01 --end 2024-03-31 --refresh
```

### Output Files

All reports are saved to `backtesting/reports/`:

- **Full Report** - `backtest_report_[name].txt` - Comprehensive analysis
- **Trades CSV** - `trades_[name].csv` - All trade details for Excel analysis
- **Results JSON** - `results_[name].json` - Raw data for programmatic access

## Understanding Results

### Key Metrics Explained

#### Returns
- **Total Return %**: Overall percentage gain/loss
- **CAGR**: Compound Annual Growth Rate (annualized returns)
- **Total PnL**: Dollar profit/loss

#### Risk Metrics
- **Sharpe Ratio**: Risk-adjusted returns (>1.0 good, >2.0 excellent)
- **Sortino Ratio**: Like Sharpe, but only penalizes downside volatility
- **Max Drawdown**: Largest peak-to-trough decline
- **Calmar Ratio**: CAGR / Max Drawdown (higher is better)

#### Trade Statistics
- **Win Rate**: Percentage of winning trades
- **Profit Factor**: Gross profit / Gross loss (>1.5 is good)
- **Expectancy**: Average $ per trade (must be positive)
- **Kelly %**: Optimal position size according to Kelly Criterion

#### Risk/Reward
- **Avg R:R**: Average risk/reward ratio achieved
- **MFE**: Max Favorable Excursion (how far trades moved in your favor)
- **MAE**: Max Adverse Excursion (how far trades moved against you)
- **MFE/MAE Ratio**: Measures trade management efficiency

### What Makes a Good System?

| Metric | Minimum | Good | Excellent |
|--------|---------|------|-----------|
| Win Rate | 40% | 50-60% | >60% |
| Profit Factor | 1.5 | 2.0 | >3.0 |
| Sharpe Ratio | 1.0 | 1.5 | >2.0 |
| Max Drawdown | <30% | <20% | <10% |
| Sample Size | 30 trades | 100 trades | >200 trades |

⚠️ **WARNING**: If your system shows:
- Profit Factor < 1.0 → Losing money, do NOT trade
- Win Rate > 80% → Likely overfitting
- Sample Size < 30 → Results not statistically significant

## Advanced Usage

### Programmatic Access

```python
from backtesting import HistoricalDataLoader, BacktestEngine, PerformanceMetrics, ReportGenerator

# Step 1: Load data
loader = HistoricalDataLoader()
sol_data = loader.load_data('SOL-USDT-SWAP', '2024-01-01', '2024-03-31')
btc_data = loader.load_data('BTC-USDT-SWAP', '2024-01-01', '2024-03-31')

# Step 2: Run backtest
engine = BacktestEngine(initial_capital=10000)
results = engine.run(sol_data, btc_data, '2024-01-01', '2024-03-31')

# Step 3: Calculate metrics
metrics = PerformanceMetrics.calculate_all(results, results['all_trades'])

# Step 4: Generate reports
report_gen = ReportGenerator()
report_gen.generate_full_report(results, metrics, 'my_test')
```

### Cache Management

```python
from backtesting import HistoricalDataLoader

loader = HistoricalDataLoader()

# Clear cache for specific symbol
loader.clear_cache('SOL-USDT-SWAP')

# Clear all cache
loader.clear_cache()

# Check cache info
info = loader.get_cache_info()
print(f"Cache size: {info['total_size_mb']:.2f} MB")
```

## Interpreting Filter Analysis

The backtest tracks which filters reject the most signals. Example:

```
FILTER REJECTION BREAKDOWN:
  macro_driver: 45 rejections (35%)
  checklist: 32 rejections (25%)
  multi_timeframe: 20 rejections (15%)
  ...
```

**What This Means**:
- If one filter rejects >50% → That filter might be too strict
- If all filters combined reject >90% → System is over-filtered
- If filters reject <10% → Filters might not be selective enough

**Recommended Filter Pass Rate**: 10-30%

## Common Issues & Solutions

### Issue: "No data available"
**Solution**: Check API credentials, ensure symbols are correct, try `--refresh`

### Issue: "Insufficient sample size"
**Solution**: Test longer time periods (3-6 months minimum)

### Issue: "Filter pass rate too low"
**Solution**: Review filter thresholds in `config.py`, consider loosening

### Issue: "Negative expectancy"
**Solution**: System is losing money, don't trade live, revise strategy

## Best Practices

### 1. Test Multiple Time Periods
```bash
# Test Q1 2024
python run_backtest.py --start 2024-01-01 --end 2024-03-31 --name q1_2024

# Test Q2 2024
python run_backtest.py --start 2024-04-01 --end 2024-06-30 --name q2_2024

# Compare results across periods
```

### 2. Walk-Forward Testing
- Train on Jan-Mar, test on Apr
- Train on Jan-Apr, test on May
- Train on Jan-May, test on Jun
- Prevents overfitting

### 3. Out-of-Sample Testing
- Optimize on 2023 data
- Test on 2024 data (unseen)
- If performance degrades significantly → Overfitting

### 4. Stress Testing
Test on different market conditions:
- Bull markets
- Bear markets
- High volatility periods
- Low volatility periods

### 5. Monte Carlo Simulation
Run backtest 100+ times with randomized entry times (+/- 1-2 bars) to test robustness.

## Validation Checklist

Before considering a system for live trading:

- [ ] Tested on 6+ months of data
- [ ] Minimum 100 trades executed
- [ ] Profit Factor > 1.5
- [ ] Sharpe Ratio > 1.0
- [ ] Max Drawdown < 20%
- [ ] Walk-forward tested (3+ periods)
- [ ] Out-of-sample tested
- [ ] Stress tested (bull/bear/volatile)
- [ ] Reviewed all filter rejections
- [ ] Analyzed trade-by-trade details
- [ ] Paper traded for 30-90 days
- [ ] Started live with reduced size

## Performance Benchmarks

Compare your system against these benchmarks:

| Strategy Type | Expected Win Rate | Expected Profit Factor | Expected Sharpe |
|---------------|-------------------|------------------------|-----------------|
| Trend Following | 30-40% | 2.0-3.0 | 0.5-1.5 |
| Mean Reversion | 55-65% | 1.5-2.0 | 1.0-2.0 |
| Breakout | 35-45% | 2.0-2.5 | 0.8-1.8 |
| Our System (Elite Quant) | 50-60% | >2.0 | >1.5 |

## Troubleshooting

### ImportError
```bash
# Install dependencies
pip install numpy pandas scikit-learn requests python-dotenv
```

### API Rate Limits
- Data is cached automatically
- Use `--refresh` only when needed
- Wait 1 minute between refreshes

### Memory Issues
- Test shorter periods (1-3 months)
- Use higher timeframes only (disable 1m)
- Clear cache periodically

## Support & Documentation

- Full system docs: See main README.md
- Config settings: See config.py
- Filter details: See filters/ directory
- Strategy logic: See strategy/ directory

## Next Steps After Backtesting

1. **If Results Are Good** (Profitable, good metrics):
   - Run walk-forward tests
   - Paper trade for 30-90 days
   - Start live with 0.25% risk (half of normal)

2. **If Results Are Marginal** (Slightly profitable):
   - Review filter rejections
   - Tune thresholds
   - Test longer periods
   - Consider strategy modifications

3. **If Results Are Bad** (Unprofitable):
   - Review trade-by-trade details
   - Check if filters are working correctly
   - Verify strategy logic
   - May need major revision
   - DO NOT trade live

---

**Remember**: Backtest results are historical. Past performance does not guarantee future results. Always paper trade before going live.
