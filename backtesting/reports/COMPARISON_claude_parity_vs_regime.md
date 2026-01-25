# Backtest Comparison: Claude-Testing Parity vs + Regime

**Period:** 2025-11-01 → 2025-12-31 (same for both)  
**Capital:** $10,000  
**Config:** Same system as claude-testing (live). Regime is the **only** difference.

---

## Summary

| Metric | Baseline (claude-testing) | + Regime | Δ |
|--------|---------------------------|----------|---|
| **Total Return** | **-36.41%** | **+50.92%** | **+87.3 pp** |
| Final Capital | $6,358.89 | $15,092.11 | +$8,733 |
| Trades Executed | 301 | 29 | -272 |
| Win Rate | 39.53% | 48.28% | +8.8 pp |
| Profit Factor | 0.92 | 1.76 | +0.84 |
| Sharpe Ratio | 0.77 | 3.26 | +2.49 |
| Max Drawdown | 59.71% | 15.11% | -44.6 pp |
| Expectancy/trade | -$12.40 | +$160.13 | +$172.53 |

---

## Strategy Breakdown

### Baseline (no regime)
| Strategy | Trades | Wins | PnL |
|----------|--------|------|-----|
| MEANREVERSION | 27 | 12 (44.4%) | +$1,361.77 |
| BREAKOUTV3 | 2 | 1 (50.0%) | -$81.18 |
| **HFT_SCALPING** | **272** | **106 (39.0%)** | **-$5,013.19** |
| **Total** | 301 | 119 | **-$3,732.60** |

### + Regime
| Strategy | Trades | Wins | PnL |
|----------|--------|------|-----|
| MEANREVERSION | 26 | 12 (46.2%) | +$3,501.17 |
| BREAKOUTV3 | 3 | 2 (66.7%) | +$1,142.52 |
| **HFT_SCALPING** | **0** | — | **$0** (disabled in RANGING) |
| **Total** | 29 | 14 | **+$4,643.69** |

---

## Takeaways

1. **Same system:** Identical config, filters, strategies, Prediction V1, HFT, etc. Only `BACKTEST_REGIME_ADAPTIVE` differs (OFF vs ON).

2. **Regime effect:** In this Nov–Dec window the market was **~98% RANGING**. Regime turns **HFT off** in RANGING. Result:
   - **272 HFT trades removed** (those lost ~\$5k).
   - MR + Breakout continue; MR does better with regime (larger avg win, similar trade count).

3. **Return flip:** Baseline **-36.4%** → Regime **+50.9%** on the same period.

4. **Risk:** Max DD drops from **59.7%** to **15.1%**; Sharpe **0.77 → 3.26**.

5. **Claude-testing unchanged:** No edits to live / claude-testing code or config. All changes are backtest-only (regime + HFT gating in regime).

---

## Reports

- Baseline: `backtest_report_claude_parity_baseline.txt`
- + Regime: `backtest_report_claude_parity_plus_regime.txt`
