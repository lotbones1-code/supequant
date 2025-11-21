# 🚀 Elite Quant Trading System

A professional-grade automated cryptocurrency trading system designed for **high accuracy** and **low trade frequency**. Built with extreme filtering to ensure only the highest-probability setups are traded.

## 🎯 Philosophy

**Quality over Quantity**
- 3-5 trades per day maximum
- Multiple layers of filters reject 95%+ of potential trades
- Only trade when ALL conditions align perfectly
- Heavy focus on risk management

## ⚙️ System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MARKET DATA FEED                     │
│          (OKX API - Multi-timeframe data)               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   FILTER SYSTEM                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  1. Market Regime Filter                         │   │
│  │     ✓ ATR volatility check                       │   │
│  │     ✓ Funding rate validation                    │   │
│  │     ✓ Open interest stability                    │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  2. Multi-Timeframe Filter                       │   │
│  │     ✓ HTF trend alignment                        │   │
│  │     ✓ MTF confirmation                           │   │
│  │     ✓ LTF entry timing                           │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  3. AI Rejection Filter                          │   │
│  │     ✓ ML model confidence scoring                │   │
│  │     ✓ Pattern feature analysis                   │   │
│  │     ✓ Rule-based fallback                        │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  4. Pattern Failure Filter                       │   │
│  │     ✓ Bull/bear trap detection                   │   │
│  │     ✓ Stop hunt identification                   │   │
│  │     ✓ Fakeout recognition                        │   │
│  │     ✓ Low liquidity spike rejection              │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────┘
                      │
         ALL FILTERS MUST PASS ✅
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  STRATEGY LAYER                         │
│   • Breakout Strategy (volatility compression)          │
│   • Pullback Strategy (trend continuation)              │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                 RISK MANAGEMENT                         │
│   • Position sizing (0.5% risk per trade)               │
│   • Daily loss limits (2.5% max)                        │
│   • Max 1 position open                                 │
│   • Emergency shutdown logic                            │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              EXECUTION & TRACKING                       │
│        (OKX API - Order placement & monitoring)         │
└─────────────────────────────────────────────────────────┘
```

## 🔧 Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd supequant
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API credentials

```bash
# Copy the template
cp .env.template .env

# Edit .env with your OKX API credentials
nano .env
```

**Important:** Get your API keys from [OKX](https://www.okx.com/account/my-api)

### 4. Review configuration

Edit `config.py` to adjust:
- Trading parameters
- Risk limits
- Timeframe settings
- Filter thresholds

## 🚀 Usage

### Start the system

```bash
python main.py
```

### Start in demo mode (recommended first)

Make sure `OKX_SIMULATED=True` in your `.env` file.

### Monitor logs

```bash
# Main log
tail -f logs/trading.log

# Trade log
tail -f logs/trades.log

# Filter decisions
tail -f logs/filters.log
```

## 📊 Key Features

### Heavy Filtering System
- **4 independent filters** that ALL must pass
- Market regime validation
- Multi-timeframe trend alignment
- AI-based confidence scoring
- Pattern failure detection

### Risk Management
- **0.5% risk per trade** (configurable)
- **Maximum 1 position open**
- **2.5% daily loss limit**
- Emergency shutdown on extreme conditions
- Kill switch file support

### Strategies

#### Breakout Strategy
- Trades breakouts from consolidation
- Requires volatility compression
- Volume confirmation mandatory
- Clean breakout validation

#### Pullback Strategy
- Trades pullbacks in strong trends
- Fibonacci retracement levels
- Trend resumption signals
- Higher timeframe alignment

### AI Learning System
- Collects all trade predictions
- Tracks outcomes automatically
- Trains rejection model
- Improves over time

## 📁 Project Structure

```
supequant/
├── config.py              # Global configuration
├── main.py                # Main entry point
├── requirements.txt       # Python dependencies
│
├── data_feed/            # Market data acquisition
│   ├── okx_client.py     # OKX API wrapper
│   ├── market_data.py    # Data aggregation
│   └── indicators.py     # Technical indicators
│
├── filters/              # Trade filtering (MOST IMPORTANT)
│   ├── market_regime.py  # Market condition filter
│   ├── multi_timeframe.py # Timeframe alignment
│   ├── ai_rejection.py   # AI confidence filter
│   ├── pattern_failure.py # Trap pattern detection
│   └── filter_manager.py # Filter orchestration
│
├── strategy/             # Trading strategies
│   ├── breakout_strategy.py
│   ├── pullback_strategy.py
│   └── strategy_manager.py
│
├── execution/            # Order execution
│   ├── order_manager.py  # Order placement
│   └── position_tracker.py # Position tracking
│
├── risk/                 # Risk management
│   └── risk_manager.py
│
├── model_learning/       # AI model training
│   ├── data_collector.py
│   └── model_trainer.py
│
└── utils/                # Utilities
    └── logger.py
```

## ⚠️ Important Safety Notes

1. **Always start in simulated mode** (`OKX_SIMULATED=True`)
2. **Never commit your `.env` file** (contains API keys)
3. **Test thoroughly** before going live
4. **Monitor the first few trades closely**
5. **Use the kill switch** (`touch KILL_SWITCH.txt`) to stop trading immediately

## 🎛️ Configuration Guide

### Key Settings in `config.py`

```python
# Risk Management
MAX_RISK_PER_TRADE = 0.005      # 0.5% risk per trade
MAX_POSITIONS_OPEN = 1          # Only 1 position at a time
MAX_DAILY_LOSS_PCT = 0.025      # 2.5% max daily loss

# Filters
AI_CONFIDENCE_THRESHOLD = 70    # Minimum AI confidence (0-100)
ATR_MIN_PERCENTILE = 20         # Minimum volatility
ATR_MAX_PERCENTILE = 80         # Maximum volatility

# Strategy
BREAKOUT_VOLUME_MULTIPLIER = 1.5
PULLBACK_FIBONACCI_LEVELS = [0.382, 0.5, 0.618]
```

## 📈 Performance Tracking

The system logs:
- All filter decisions
- Every trade with full details
- Position PnL tracking
- Win rate and statistics

Check `logs/` directory for detailed information.

## 🔮 Future Enhancements (Part 2, 3, 4, 5)

This is **Part 1: Core System**. Future additions:

- **Part 2**: AI model training pipeline
- **Part 3**: Backtesting harness
- **Part 4**: Hyperparameter optimization
- **Part 5**: Telegram alerts and monitoring

## 🤝 Contributing

This is a private trading system. Modify carefully and always test changes in simulated mode first.

## 📝 License

Private/Proprietary

## 🆘 Support

For issues or questions, refer to:
- Logs in `logs/` directory
- Configuration in `config.py`
- OKX API documentation: https://www.okx.com/docs-v5/en/

---

**Remember:** This system is designed to trade RARELY but with HIGH ACCURACY. If you're not getting many trades, that's BY DESIGN. The heavy filtering ensures only the best setups are traded.

**Good luck and trade responsibly!** 🚀
