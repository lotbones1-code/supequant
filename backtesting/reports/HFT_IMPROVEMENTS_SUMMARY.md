# HFT Aggressive Improvements - Backtest Comparison

## Test Period
- **Window**: 2025-11-23 to 2025-12-10 (17 days)
- **Previous Run**: `hft_daily_short_window_loose`
- **New Run**: `hft_aggressive_improved`

## Changes Implemented

1. **Filter Manager**: Added early return for HFT signals to bypass quality-score and pattern-failure gates
2. **Config**: Lowered `HFT_SCORE_THRESHOLD` from 45 to 39
3. **Strategy**: Widened stops/targets:
   - Stop: 0.25% → 0.32%
   - TP1: 0.35% → 0.47%
   - TP2: 0.60% → 0.85%
4. **Quality Filters**: Added optional filters (enabled by default):
   - Simple regime filter (skip longs if 1h/4h down, shorts if up) - threshold 0.4
   - Market open cooldown (8 minutes)
   - Overheat filter (skip if range > 2.5x ATR)

## Results Comparison

| Metric | Previous Run | New Run | Change |
|--------|-------------|---------|--------|
| **Total Return** | +7.22% | +6.12% | -1.10% |
| **Profit Factor** | 1.10 | 1.07 | -0.03 |
| **Trade Count** | 24 | 24 | 0 |
| **Win Rate** | 41.67% | 41.67% | 0% |
| **Sharpe Ratio** | 0.96 | 0.96 | 0 |
| **Max Drawdown** | 16.47% | 16.60% | +0.13% |
| **Expectancy** | $16.78/trade | $12.31/trade | -$4.47 |

## Analysis

### Trade Count
- **Same trade count (24)**: The changes did not increase trade volume
- This suggests HFT signals may not be generating frequently in this period, or other strategies are being selected instead

### Performance
- **Slight degradation**: Return decreased by 1.10% and PF decreased by 0.03
- **Same win rate**: 41.67% maintained
- **Lower expectancy**: Average profit per trade decreased by $4.47

### Possible Reasons
1. **HFT signals not generating**: The 1m breakout conditions may not have been met frequently
2. **Strategy selection**: Strategy manager may be prioritizing other strategies (Mean Reversion, Breakout) over HFT
3. **Filter bypass working**: HFT signals may be bypassing filters but still not being selected due to strategy priority
4. **Wider stops**: The wider stops (0.32% vs 0.25%) may have allowed more losses to hit stop before reaching targets

## Recommendations

1. **Verify HFT signal generation**: Check logs to confirm HFT signals are being generated
2. **Strategy priority**: Ensure HFT signals are being selected when generated (they should have priority 0 in strategy manager)
3. **Tune stops**: Consider tightening stops back to 0.30% if losses are hitting stops too frequently
4. **Longer test period**: Test over a longer period (60+ days) to get more statistical significance
5. **Monitor filter bypass**: Verify that HFT signals are actually bypassing quality gates as intended

## Files Modified

- `filters/filter_manager.py`: Added HFT early return bypass
- `config.py`: Lowered HFT_SCORE_THRESHOLD to 39, added quality filter configs
- `strategy/high_freq_scalping.py`: Widened stops/targets, added quality filters
- `backtesting/backtest_engine.py`: Updated to pass signal to filter_manager
- `main.py`: Updated to pass signal to filter_manager

## Next Steps

1. Run backtest with logging enabled to see HFT signal generation
2. Test over longer period (60-90 days) for better statistics
3. Consider adjusting stop/target ratios if needed
4. Verify HFT strategy is being called and signals generated
