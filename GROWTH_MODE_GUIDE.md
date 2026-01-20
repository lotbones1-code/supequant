# 🚀 Aggressive Growth Mode Guide

## Overview

Growth Mode is designed to turn small accounts ($5) into large ones ($1,000+) through:
- **Compound Growth**: Position sizes increase as your account grows
- **Confidence-Based Sizing**: Bigger positions on high-confidence setups
- **Leverage Optimization**: Safe leverage usage (3x default, up to 10x)
- **Aggressive TP Targets**: 3R, 5R, 8R targets for maximum gains

## How It Works

### 1. Compound Growth
As your account grows, position sizes automatically scale up:
- Starting: $5 account → 1% risk = $0.05 per trade
- At $50: Position sizes increase ~2x
- At $500: Position sizes increase ~3x
- Maximum: Up to 5% risk per trade (configurable)

### 2. Confidence Multipliers
High-confidence setups get bigger positions:
- **Confidence ≥ 0.8**: 2.0x position size
- **Confidence ≥ 0.7**: 1.5x position size
- **Confidence ≥ 0.6**: 1.2x position size
- **Confidence < 0.5**: 0.5x position size (reduced)

### 3. Win Streak Boosters
After consecutive wins, position sizes increase:
- **3 wins**: +20% position size
- **5 wins**: +50% position size

### 4. Loss Streak Protection
After losses, position sizes reduce:
- **2 losses**: -30% position size
- **3 losses**: -50% position size

### 5. Leverage
- **Default**: 3x leverage (safe)
- **Maximum**: 10x leverage (aggressive)
- Uses **isolated margin** to protect account

### 6. Aggressive TP Targets
- **TP1**: 3:1 risk/reward (40% of position)
- **TP2**: 5:1 risk/reward (35% of position)
- **TP3**: 8:1 risk/reward (25% of position)

## Configuration

### Enable Growth Mode

```python
# In config.py or .env
GROWTH_MODE_ENABLED = True
```

### Adjust Settings

```python
# Base risk (starting point)
GROWTH_BASE_RISK_PCT = 0.01  # 1%

# Maximum risk (cap)
GROWTH_MAX_RISK_PCT = 0.05  # 5%

# Leverage
GROWTH_LEVERAGE = 3  # 3x (safe) to 10x (aggressive)

# Features
GROWTH_COMPOUND_ENABLED = True  # Compound growth
GROWTH_CONFIDENCE_MULTIPLIER = True  # Confidence-based sizing
GROWTH_AGGRESSIVE_TP = True  # Aggressive TP targets
```

## Example: $5 → $1,000 Journey

### Starting Point
- **Account**: $5
- **Risk per trade**: $0.05 (1%)
- **Position size**: ~$0.15 (with 3x leverage)
- **TP targets**: 3R, 5R, 8R

### After 10 Winning Trades (60% win rate)
- **Account**: ~$50
- **Risk per trade**: $0.50 (1% of $50)
- **Position size**: ~$1.50 (with 3x leverage)
- **Growth multiplier**: ~2x

### After 30 Winning Trades
- **Account**: ~$500
- **Risk per trade**: $5 (1% of $500)
- **Position size**: ~$15 (with 3x leverage)
- **Growth multiplier**: ~3x

### After 50 Winning Trades
- **Account**: ~$1,000+
- **Risk per trade**: $10 (1% of $1,000)
- **Position size**: ~$30 (with 3x leverage)
- **Growth multiplier**: ~4x

## Safety Features

### 1. Maximum Risk Cap
- Never risks more than `GROWTH_MAX_RISK_PCT` (default: 5%)
- Prevents over-leveraging

### 2. Loss Streak Protection
- Automatically reduces position size after losses
- Prevents account destruction

### 3. Isolated Margin
- Leverage uses isolated margin
- Limits losses to position size only

### 4. Stop Loss Always Active
- Every trade has a stop loss
- Protects against catastrophic losses

### 5. Daily Loss Limits
- Still respects `MAX_DAILY_LOSS_PCT` (5%)
- Stops trading if daily loss limit hit

## Best Practices

### 1. Start Small
- Begin with $5-10
- Test the system
- Scale up as you gain confidence

### 2. Monitor Performance
- Track win rate (aim for >60%)
- Monitor growth multiplier
- Adjust leverage based on performance

### 3. Use High Confidence Setups
- Focus on high-confidence trades
- These get bigger positions automatically
- Better win rate = faster growth

### 4. Let Winners Run
- Aggressive TP targets (3R, 5R, 8R)
- Don't exit early
- Let compound growth work

### 5. Protect Capital
- Respect stop losses
- Don't override safety features
- If losing, reduce leverage

## Monitoring Growth

### Check Growth Stats

```python
stats = risk_manager.get_risk_statistics()
growth_stats = stats.get('growth_stats', {})

print(f"Starting: ${growth_stats['starting_balance']:.2f}")
print(f"Current: ${growth_stats['current_balance']:.2f}")
print(f"Growth: {growth_stats['total_growth_pct']:.1f}%")
print(f"Multiplier: {growth_stats['growth_multiplier']:.2f}x")
```

### Logs Show

```
🚀 Growth-optimized position:
   Base: 0.0015
   Growth multiplier: 2.50x
   Confidence multiplier: 2.00x
   Streak multiplier: 1.20x
   Final (with 3x leverage): 0.0270
```

## Risk Warning

⚠️ **Aggressive growth = Higher risk**

- Leverage amplifies both gains AND losses
- Higher position sizes = bigger losses if wrong
- Requires discipline and risk management
- Not suitable for all traders

**Recommendation**: Start with 3x leverage, test thoroughly, then consider increasing if performance is good.

## Disable Growth Mode

If you want to return to conservative trading:

```python
GROWTH_MODE_ENABLED = False
```

This returns to standard 1% risk, no leverage, conservative TP targets.

## Summary

✅ **Compound growth** - Positions scale with account  
✅ **Confidence multipliers** - Bigger on high-confidence setups  
✅ **Leverage optimization** - 3x-10x safely  
✅ **Aggressive TP** - 3R, 5R, 8R targets  
✅ **Safety features** - Risk caps, loss protection, stop losses  

**Goal**: Turn $5 into $1,000+ through disciplined, aggressive growth! 🚀
