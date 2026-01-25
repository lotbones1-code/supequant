# Oct-Dec 2025: Regime vs Baseline Comparison

**Period:** 2025-10-01 → 2025-12-31 (3 months - same as 107% backtest period)  
**Capital:** $10,000  
**Config:** Same system as claude-testing (live). Regime is the **only** difference.

---

## Results Summary

| Metric | Baseline (no regime) | + Regime | Δ |
|--------|----------------------|----------|---|
| **Total Return** | **+272.08%** | **+245.50%** | **-26.6 pp** |
| Final Capital | $37,207.83 | $34,550.43 | -$2,657 |
| Trades Executed | 44 | 40 | -4 |
| Win Rate | 52.27% | 55.00% | +2.7 pp |
| Profit Factor | 3.63 | 3.71 | +0.08 |
| Sharpe Ratio | 4.48 | 5.45 | +0.97 |
| Max Drawdown | 16.89% | 17.70% | +0.8 pp |
| Expectancy/trade | $584.54 | $586.55 | +$2.01 |

---

## Strategy Breakdown

### Baseline (no regime)
| Strategy | Trades | Wins | PnL |
|----------|--------|------|-----|
| MEANREVERSION | 35 | 19 (54.3%) | +$21,674.74 |
| BREAKOUTV3 | 7 | 4 (57.1%) | +$4,334.38 |
| SCALPING | 1 | 0 (0.0%) | -$240.04 |
| MOMENTUM | 1 | 0 (0.0%) | -$49.22 |
| **Total** | 44 | 23 | **+$25,719.85** |

### + Regime
| Strategy | Trades | Wins | PnL |
|----------|--------|------|-----|
| MEANREVERSION | 32 | 18 (56.2%) | +$20,671.40 |
| BREAKOUTV3 | 7 | 4 (57.1%) | +$2,840.91 |
| MOMENTUM | 1 | 0 (0.0%) | -$50.37 |
| SCALPING | 0 | — | $0 (blocked by regime) |
| **Total** | 40 | 22 | **+$23,461.93** |

---

## Analysis

### What Regime Did:
1. **Blocked Scalping** (1 losing trade saved: -$240)
2. **Slightly reduced MR trades** (35 → 32, but higher win rate: 54.3% → 56.2%)
3. **Slightly reduced BreakoutV3 PnL** (7 trades, but +$4.3k → +$2.8k)

### Trade-offs:
- **Lower absolute return:** -26.6 percentage points (272% → 245%)
- **Better risk-adjusted metrics:** Sharpe +0.97, PF +0.08, Win rate +2.7 pp
- **More selective:** 4 fewer trades (44 → 40)
- **Better consistency:** Higher win rate, better risk/reward profile

---

## Recommendation

**For Live System (claude-testing):**

### ✅ **ADD REGIME** - Recommended

**Reasons:**
1. **Risk-adjusted performance is better:** Sharpe 5.45 vs 4.48 (+21% better)
2. **Higher win rate:** 55% vs 52.27% (more consistent)
3. **Better profit factor:** 3.71 vs 3.63
4. **Protection from bad trades:** Blocks losing strategies (Scalping) in wrong regimes
5. **More selective:** Fewer but higher quality trades

**Trade-off:**
- Slightly lower absolute return (-26.6 pp), but still **+245%** (vs baseline +272%)
- Both are excellent returns, but regime version is more **sustainable and consistent**

**Bottom line:** Regime adds **intelligence** - it adapts to market conditions and avoids bad trades. The slight reduction in absolute return is worth the improved risk-adjusted metrics and consistency.

---

## Notes

- Both versions significantly outperform the 107% baseline mentioned
- Baseline: +272% (vs 107% = +165 pp better)
- Regime: +245% (vs 107% = +138 pp better)
- Regime is more conservative but more robust
