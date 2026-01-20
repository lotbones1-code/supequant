"""
Backtest Engine
Replays historical data through strategies and filters to validate system performance

This is the core backtesting logic that:
- Simulates real-time market conditions
- Runs strategies to generate signals
- Validates signals through ALL filters
- Simulates trade execution with realistic slippage
- Tracks outcomes and calculates PnL
- Collects comprehensive statistics
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import copy

from strategy.breakout_strategy import BreakoutStrategy
from strategy.breakout_strategy_v2 import BreakoutStrategyV2
from strategy.breakout_strategy_v3 import BreakoutStrategyV3
from strategy.pullback_strategy import PullbackStrategy
from strategy.mean_reversion import MeanReversionStrategy
from strategy.momentum_strategy import MomentumStrategy
from strategy.structure_strategy import StructureStrategy
# Backtest-only strategies
from backtesting.trend_following_strategy import TrendFollowingStrategy
# Fair AI evaluation (no future data cheating)
from backtesting.ai_backtest_fair import create_fair_ai_evaluator
# Smart Multi-Timeframe Intelligence (backtest only)
from backtesting.smart_mtf_checker import create_mtf_checker
# ML-based trade scoring (backtest only)
from backtesting.ml_trade_scorer import create_ml_scorer
# Fear & Greed Index (backtest only)
from backtesting.fear_greed_backtest import create_fear_greed_backtester
# Note: FundingArbitrageStrategy excluded - requires live funding rate data not in historical candles
from filters.filter_manager import FilterManager
from data_feed.indicators import TechnicalIndicators
import config

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """
    Represents a single backtest trade with all details
    """
    # Entry details
    signal_id: str
    timestamp: datetime
    symbol: str
    direction: str  # 'long' or 'short'
    strategy: str
    entry_price: float
    stop_price: float
    target_price: float  # Legacy single TP (for backward compatibility)
    position_size: float  # Number of contracts

    # Multiple TP levels (V3 support)
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    position_split: Dict = field(default_factory=lambda: {1: 0.5, 2: 0.3, 3: 0.2})  # 50/30/20 default
    
    # Position tracking for partial exits
    remaining_position: float = 0.0  # Remaining position size after partial exits
    tp1_exited: bool = False
    tp2_exited: bool = False
    tp3_exited: bool = False
    partial_exits_pnl: float = 0.0  # Cumulative PnL from partial exits

    # Filter results
    filter_results: Dict = field(default_factory=dict)
    filter_passed: bool = True

    # Execution details
    executed: bool = False
    entry_slippage: float = 0.0
    actual_entry_price: float = 0.0

    # Exit details
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # 'target', 'stop', 'timeout', 'tp1', 'tp2', 'tp3'
    bars_held: int = 0

    # Performance
    pnl_points: float = 0.0
    pnl_percent: float = 0.0
    pnl_dollar: float = 0.0
    win: bool = False

    # Risk metrics
    max_favorable_excursion: float = 0.0  # MFE
    max_adverse_excursion: float = 0.0  # MAE
    risk_reward_achieved: float = 0.0


class RegimeTracker:
    """
    Tracks market regime over time and determines when Mean Reversion should be active.
    
    BACKTEST ONLY - Not used in live system.
    
    NEW LOGIC (v2):
    - Tracks trend strength readings over a rolling window
    - Mean Reversion only enabled if NO trending readings in recent window
    - This is a "one strike and you're out" approach for trending
    """
    
    def __init__(self, window_size: int = 96, trend_threshold: float = 0.35):
        """
        Args:
            window_size: Number of candles to track (96 = 24 hours at 15m)
            trend_threshold: Trend strength above this = trending market
        """
        self.window_size = window_size
        self.trend_threshold = trend_threshold
        self.trend_readings: List[float] = []
        self.regime_history: List[str] = []  # 'trending' or 'ranging'
        
        # State
        self.current_regime = 'unknown'
        self.mean_reversion_enabled = False  # Start disabled, earn the right to trade
        self.regime_changes = 0
        
        # Cooldown: how many candles of ranging needed after trending before MR can trade
        self.cooldown_candles = 24  # 6 hours at 15m
        self.candles_since_trending = 0
        
        logger.info(f"📊 RegimeTracker v2 initialized (window={window_size}, threshold={trend_threshold}, cooldown={self.cooldown_candles})")
    
    def update(self, market_state: Dict) -> float:
        """
        Update regime tracker with new market data.
        
        Option 2: Returns CONFIDENCE level (0-1) for position sizing
        - High confidence (>0.7): Full position size
        - Medium confidence (0.4-0.7): Half position size  
        - Low confidence (<0.4): Skip or minimal size
        
        Returns:
            Confidence level 0-1 for Mean Reversion
        """
        # Extract trend strength from 15m and 1H timeframes
        timeframes = market_state.get('timeframes', {})
        
        # Get 15m trend
        tf_15m = timeframes.get('15m', {})
        trend_15m = tf_15m.get('trend', {})
        strength_15m = trend_15m.get('trend_strength', 0)
        
        # Get 1H trend (weighted more heavily)
        tf_1h = timeframes.get('1H', {})
        trend_1h = tf_1h.get('trend', {})
        strength_1h = trend_1h.get('trend_strength', 0)
        
        # Combine with 1H having more weight
        combined_strength = (strength_15m * 0.4) + (strength_1h * 0.6)
        
        # Track for statistics
        self.trend_readings.append(combined_strength)
        if len(self.trend_readings) > self.window_size:
            self.trend_readings.pop(0)
        
        # Calculate regime confidence (inverse of trend strength)
        # Higher trend = lower MR confidence
        # combined_strength 0 = MR confidence 1.0
        # combined_strength 0.5 = MR confidence 0.5
        # combined_strength 1.0 = MR confidence 0.0
        base_confidence = max(0, 1 - (combined_strength * 2))
        
        # Boost confidence if we've had sustained ranging
        if len(self.trend_readings) >= self.cooldown_candles:
            recent = self.trend_readings[-self.cooldown_candles:]
            avg_recent = sum(recent) / len(recent)
            if avg_recent < self.trend_threshold:
                base_confidence = min(1.0, base_confidence + 0.2)
        
        # Reduce confidence if recent readings show trending
        if len(self.trend_readings) >= 8:
            recent_8 = self.trend_readings[-8:]
            trending_count = sum(1 for s in recent_8 if s > self.trend_threshold)
            if trending_count >= 4:
                base_confidence = max(0, base_confidence - 0.3)
        
        # Update state for logging
        if base_confidence > 0.7:
            self.current_regime = 'ranging'
        elif base_confidence > 0.3:
            self.current_regime = 'uncertain'
        else:
            self.current_regime = 'trending'
        
        self.regime_history.append(self.current_regime)
        return base_confidence
    
    def get_stats(self) -> Dict:
        """Get regime tracking statistics"""
        if not self.regime_history:
            return {'regime_changes': 0, 'trending_pct': 0, 'ranging_pct': 0}
        
        trending = self.regime_history.count('trending')
        ranging = self.regime_history.count('ranging')
        total = len(self.regime_history)
        
        return {
            'regime_changes': self.regime_changes,
            'trending_pct': trending / total if total > 0 else 0,
            'ranging_pct': ranging / total if total > 0 else 0,
            'current_regime': self.current_regime,
            'mr_enabled': self.mean_reversion_enabled
        }


class EliteRegimeChecker:
    """
    ELITE BACKTEST ONLY - Strict regime checking for Mean Reversion
    
    Improvements:
    1. Check 1H trend strength (not just 15m)
    2. Return confidence level for position sizing
    3. Track regime for analysis
    """
    
    def __init__(self):
        self.enabled = getattr(config, 'ELITE_BACKTEST_MODE', False) and getattr(config, 'ELITE_STRICT_REGIME', False)
        self.trend_max = getattr(config, 'ELITE_1H_TREND_MAX', 0.40)
        
        # Stats tracking
        self.checks_total = 0
        self.checks_passed = 0
        self.checks_blocked = 0
        
        if self.enabled:
            logger.info(f"📊 EliteRegimeChecker: ENABLED (1H trend max: {self.trend_max})")
    
    def check(self, market_state: Dict) -> Tuple[bool, float]:
        """
        Check if Mean Reversion should trade.
        
        Returns:
            (allowed: bool, confidence: float 0-1)
        """
        if not self.enabled:
            return True, 1.0
        
        self.checks_total += 1
        
        timeframes = market_state.get('timeframes', {})
        
        # Get 1H trend (primary check)
        tf_1h = timeframes.get('1H', {})
        trend_1h = tf_1h.get('trend', {})
        strength_1h = trend_1h.get('trend_strength', 0)
        
        # Get 15m trend (secondary)
        tf_15m = timeframes.get('15m', {})
        trend_15m = tf_15m.get('trend', {})
        strength_15m = trend_15m.get('trend_strength', 0)
        
        # STRICT CHECK: Block if 1H trend is too strong
        if strength_1h > self.trend_max:
            self.checks_blocked += 1
            logger.debug(f"🚫 EliteRegime: BLOCKED - 1H trend {strength_1h:.2f} > {self.trend_max}")
            return False, 0.0
        
        # Calculate confidence based on trend strength
        # Lower trend = higher confidence for MR
        # strength_1h = 0.0 → confidence = 1.0
        # strength_1h = 0.4 → confidence = 0.5
        confidence = max(0, 1.0 - (strength_1h / self.trend_max) * 0.5)
        
        # Reduce confidence if 15m also shows trend
        if strength_15m > 0.3:
            confidence *= 0.8
        
        self.checks_passed += 1
        return True, confidence
    
    def get_stats(self) -> Dict:
        """Get regime checking statistics"""
        return {
            'total_checks': self.checks_total,
            'passed': self.checks_passed,
            'blocked': self.checks_blocked,
            'block_rate': self.checks_blocked / self.checks_total if self.checks_total > 0 else 0
        }


class EliteConfirmationChecker:
    """
    ELITE BACKTEST ONLY - Confirmation candle requirement
    
    Waits for reversal confirmation before entering:
    - For LONG: Wait for green candle after signal
    - For SHORT: Wait for red candle after signal
    """
    
    def __init__(self):
        self.enabled = getattr(config, 'ELITE_BACKTEST_MODE', False) and getattr(config, 'ELITE_REQUIRE_CONFIRMATION', False)
        self.bars_required = getattr(config, 'ELITE_CONFIRMATION_BARS', 2)
        
        # Track pending signals waiting for confirmation
        self.pending_signals: Dict[str, Dict] = {}  # signal_id -> signal_data
        
        # Stats
        self.signals_confirmed = 0
        self.signals_expired = 0
        
        if self.enabled:
            logger.info(f"📊 EliteConfirmation: ENABLED (require {self.bars_required} bars)")
    
    def check_confirmation(self, candles: List[Dict], direction: str) -> bool:
        """
        Check if recent candles confirm the reversal.
        
        Less strict: Just need the MOST RECENT candle to be a reversal candle,
        not ALL candles in the window.
        
        Args:
            candles: Recent candles (most recent last)
            direction: 'long' or 'short'
            
        Returns:
            True if confirmation found
        """
        if not self.enabled or len(candles) < 1:
            return True  # Disabled or not enough data - allow
        
        # Just check the most recent candle
        last_candle = candles[-1]
        
        if direction == 'long':
            # Need green candle (close > open) for long confirmation
            confirmed = last_candle['close'] > last_candle['open']
        else:
            # Need red candle (close < open) for short confirmation
            confirmed = last_candle['close'] < last_candle['open']
        
        if confirmed:
            self.signals_confirmed += 1
        
        return confirmed
    
    def get_stats(self) -> Dict:
        return {
            'confirmed': self.signals_confirmed,
            'expired': self.signals_expired
        }


class BacktestEngine:
    """
    Comprehensive backtesting engine

    Simulates trading system performance on historical data
    """

    def __init__(self, initial_capital: float = 10000.0, breakout_strategy=None):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # Initialize components
        # Allow custom strategy for parameter optimization
        self.breakout_strategy = breakout_strategy if breakout_strategy else BreakoutStrategyV3()
        self.pullback_strategy = PullbackStrategy()
        
        # Initialize additional strategies (Phase 4)
        self.mean_reversion_strategy = MeanReversionStrategy() if getattr(config, 'MEAN_REVERSION_ENABLED', True) else None
        self.momentum_strategy = MomentumStrategy() if getattr(config, 'MOMENTUM_STRATEGY_ENABLED', True) else None
        self.structure_strategy = StructureStrategy() if getattr(config, 'STRUCTURE_STRATEGY_ENABLED', True) else None
        # Note: FundingArbitrageStrategy excluded - requires live funding rate data
        
        # BACKTEST ONLY: Trend Following strategy (complements Mean Reversion)
        self.trend_following_strategy = TrendFollowingStrategy() if getattr(config, 'BACKTEST_TREND_FOLLOWING', True) else None
        
        # ELITE BACKTEST: Strict regime checker
        self.elite_regime_checker = EliteRegimeChecker()
        
        # ELITE BACKTEST: Confirmation candle checker
        self.elite_confirmation_checker = EliteConfirmationChecker()
        
        # ELITE BACKTEST: Track elite stats
        self.elite_stats = {
            'regime_blocks': 0,
            'confirmation_fails': 0,
            'breakeven_stops': 0
        }
        
        # BACKTEST ONLY: Regime tracker for automatic Mean Reversion switching
        self.regime_tracker = RegimeTracker(
            window_size=getattr(config, 'REGIME_WINDOW_SIZE', 96),  # 24 hours at 15m
            trend_threshold=getattr(config, 'REGIME_TREND_THRESHOLD', 0.35)
        )
        self.use_regime_switching = getattr(config, 'BACKTEST_REGIME_SWITCHING', True)
        
        # FAIR AI BACKTEST: AI evaluation without future data cheating
        self.use_fair_ai = getattr(config, 'BACKTEST_USE_FAIR_AI', False)
        self.fair_ai_evaluator = None
        if self.use_fair_ai:
            self.fair_ai_evaluator = create_fair_ai_evaluator(
                use_claude=getattr(config, 'BACKTEST_AI_USE_CLAUDE', True),
                use_openai=getattr(config, 'BACKTEST_AI_USE_OPENAI', False)
            )
            if self.fair_ai_evaluator:
                logger.info("📊 FairAI Backtest: ENABLED")
            else:
                logger.warning("⚠️ FairAI Backtest: Failed to initialize, disabled")
                self.use_fair_ai = False
        
        # SMART MTF: Multi-Timeframe Intelligence (backtest only)
        # Now strategy-aware: different logic for Mean Reversion vs Trend Following
        self.use_mtf = getattr(config, 'BACKTEST_USE_MTF', False)
        self.mtf_checker = None
        if self.use_mtf:
            self.mtf_checker = create_mtf_checker(
                require_1h=getattr(config, 'BACKTEST_MTF_REQUIRE_1H', True),
                require_4h=getattr(config, 'BACKTEST_MTF_REQUIRE_4H', False),
                min_alignment=getattr(config, 'BACKTEST_MTF_MIN_ALIGNMENT', 0.3),
                mr_extreme_threshold=getattr(config, 'BACKTEST_MTF_MR_THRESHOLD', 0.7)
            )
            logger.info("📊 SmartMTF Backtest: ENABLED (Strategy-Aware)")
        
        # ML SCORING: Machine learning trade evaluation (backtest only)
        self.use_ml_scoring = getattr(config, 'BACKTEST_USE_ML_SCORING', False)
        self.ml_scorer = None
        if self.use_ml_scoring:
            self.ml_scorer = create_ml_scorer(
                min_score=getattr(config, 'BACKTEST_ML_MIN_SCORE', 0.4),
                adaptive=getattr(config, 'BACKTEST_ML_ADAPTIVE', True)
            )
            logger.info("🤖 ML Trade Scoring: ENABLED")
        
        # FEAR & GREED INDEX: Sentiment-based filtering (backtest only)
        self.use_fear_greed = getattr(config, 'BACKTEST_USE_FEAR_GREED', False)
        self.fear_greed_backtester = None
        if self.use_fear_greed:
            self.fear_greed_backtester = create_fear_greed_backtester(
                fear_threshold=getattr(config, 'BACKTEST_FG_FEAR_THRESHOLD', 25),
                greed_threshold=getattr(config, 'BACKTEST_FG_GREED_THRESHOLD', 75),
                block_contrarian=getattr(config, 'BACKTEST_FG_BLOCK_CONTRARIAN', True)
            )
            # Load historical data (needs network)
            if self.fear_greed_backtester.load_historical_data(days=365):
                logger.info("😱 Fear & Greed Backtest: ENABLED")
            else:
                logger.warning("⚠️ Fear & Greed: Failed to load data, disabled")
                self.use_fear_greed = False
        
        self.filter_manager = FilterManager()
        self.indicators = TechnicalIndicators()

        # Trading state
        self.open_position: Optional[BacktestTrade] = None
        self.trades: List[BacktestTrade] = []
        self.daily_trades_count = {}  # Track trades per day
        self.last_trade_time: Optional[datetime] = None

        # Statistics
        self.stats = {
            'total_signals': 0,
            'signals_passed_filters': 0,
            'signals_rejected': 0,
            'trades_executed': 0,
            'wins': 0,
            'losses': 0,
            'breakevens': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'peak_capital': initial_capital,
            'filter_rejection_counts': {}
        }

        logger.info(f"🎯 BacktestEngine initialized (capital: ${initial_capital:,.2f})")

    def run(self, sol_data: Dict, btc_data: Dict,
            start_date: str, end_date: str) -> Dict:
        """
        Run backtest on historical data

        Args:
            sol_data: SOL historical data (all timeframes)
            btc_data: BTC historical data (all timeframes)
            start_date: Start date 'YYYY-MM-DD' (requested, may differ from actual data)
            end_date: End date 'YYYY-MM-DD' (requested, may differ from actual data)

        Returns:
            Comprehensive backtest results
        """
        # Store dates as instance variables for use in _generate_results
        self.start_date = start_date
        self.end_date = end_date
        
        # Use 15m timeframe as primary iteration timeframe (good balance)
        primary_tf = '15m'
        
        # DEBUG: Log loaded candles for each symbol and timeframe
        logger.info(f"\n{'='*60}")
        logger.info(f"DEBUG: Data Loading Summary")
        logger.info(f"{'='*60}")
        
        # Log SOL data for all timeframes
        for tf_name, candles in sol_data.items():
            logger.info(f"DEBUG: Loaded {len(candles)} candles for SOL ({tf_name})")
            if candles:
                logger.info(f"  First candle: {candles[0]}")
                logger.info(f"  Last candle: {candles[-1]}")
            else:
                logger.warning(f"  ⚠️  ZERO CANDLES LOADED FOR SOL ({tf_name})!")
        
        # Log BTC data for all timeframes
        for tf_name, candles in btc_data.items():
            logger.info(f"DEBUG: Loaded {len(candles)} candles for BTC ({tf_name})")
            if candles:
                logger.info(f"  First candle: {candles[0]}")
                logger.info(f"  Last candle: {candles[-1]}")
            else:
                logger.warning(f"  ⚠️  ZERO CANDLES LOADED FOR BTC ({tf_name})!")
        
        logger.info(f"{'='*60}\n")
        
        # Get primary timeframe candles
        sol_candles = sol_data.get(primary_tf, [])

        if not sol_candles:
            logger.error("❌ No SOL data available for backtesting")
            return self._generate_results()

        # Determine actual date range from data (may differ from requested range)
        actual_start_ts = sol_candles[0]['timestamp']
        actual_end_ts = sol_candles[-1]['timestamp']
        # Store as instance variables for use in _generate_results
        self.actual_start_date = datetime.fromtimestamp(actual_start_ts / 1000).strftime('%Y-%m-%d')
        self.actual_end_date = datetime.fromtimestamp(actual_end_ts / 1000).strftime('%Y-%m-%d')
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 STARTING BACKTEST")
        logger.info(f"{'='*60}")
        logger.info(f"Requested Period: {start_date} to {end_date}")
        logger.info(f"Actual Data Period: {self.actual_start_date} to {self.actual_end_date}")
        if self.actual_start_date != start_date or self.actual_end_date != end_date:
            logger.info(f"⚠️  NOTE: Using actual data range (OKX regular candles endpoint returns recent data only)")
        logger.info(f"Initial Capital: ${self.initial_capital:,.2f}")
        logger.info(f"Symbol: {config.TRADING_SYMBOL}")
        logger.info(f"{'='*60}\n")

        total_candles = len(sol_candles)
        logger.info(f"\n📊 Data Summary:")
        logger.info(f"   Primary timeframe ({primary_tf}): {total_candles} candles")
        for tf_name, candles in sol_data.items():
            if tf_name != primary_tf:
                logger.info(f"   {tf_name}: {len(candles)} candles")
        logger.info(f"\n🚀 Processing {total_candles} candles ({primary_tf} timeframe)...\n")
        
        # DEBUG: Log backtest start info and strategy state
        logger.info(f"DEBUG: Starting backtest with {len(sol_candles)} candles")
        logger.info(f"DEBUG: Strategy indicators ready? {hasattr(self.breakout_strategy, 'df')}")
        if hasattr(self.breakout_strategy, 'df'):
            logger.info(f"  DataFrame shape: {self.breakout_strategy.df.shape}")
            logger.info(f"  Columns: {list(self.breakout_strategy.df.columns)}")
            logger.info(f"  First few rows:\n{self.breakout_strategy.df.head()}")
        else:
            logger.info(f"  Strategy does not have 'df' attribute (this is normal for BreakoutStrategyV3)")

        # Process each candle
        for idx, candle in enumerate(sol_candles):
            current_time = datetime.fromtimestamp(candle['timestamp'] / 1000)

            # Progress update every 10% (avoid division by zero)
            progress_interval = max(1, total_candles // 10)
            if idx % progress_interval == 0:
                progress = (idx / total_candles) * 100
                logger.info(f"⏳ Progress: {progress:.0f}% ({current_time.strftime('%Y-%m-%d')})")

            # Build market state up to current candle
            sol_market_state = self._build_market_state(sol_data, idx, primary_tf)
            btc_market_state = self._build_market_state(btc_data, idx, primary_tf)

            # Skip if we couldn't build market state (data alignment issues)
            if not sol_market_state or not btc_market_state:
                continue

            # Check if we have an open position
            if self.open_position:
                self._update_open_position(candle, current_time)
            else:
                # Look for new trading opportunities
                self._check_for_signals(sol_market_state, btc_market_state, current_time)

        # Close any remaining open position
        if self.open_position:
            self._force_close_position(sol_candles[-1], "backtest_end")

        # Generate final results
        results = self._generate_results()

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ BACKTEST COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"📊 Date Range Summary:")
        logger.info(f"   Requested: {start_date} to {end_date}")
        logger.info(f"   Actual Data: {self.actual_start_date} to {self.actual_end_date}")
        logger.info(f"📈 Results:")
        logger.info(f"   Signals Generated: {self.stats['total_signals']}")
        logger.info(f"   Signals Passed Filters: {self.stats['signals_passed_filters']}")
        logger.info(f"   Trades Executed: {len([t for t in self.trades if t.executed])}")
        logger.info(f"{'='*60}\n")

        return results

    def _build_market_state(self, data: Dict, current_idx: int, primary_tf: str) -> Dict:
        """
        Build market state at a specific point in time

        This simulates what the live system would see
        """
        # Bounds check
        if current_idx >= len(data[primary_tf]):
            logger.warning(f"Index {current_idx} out of bounds for {primary_tf} (len={len(data[primary_tf])})")
            return None

        market_state = {
            'timeframes': {},
            'timestamp': data[primary_tf][current_idx]['timestamp']
        }

        # For each timeframe, get candles up to current point
        for tf_name, candles in data.items():
            # Find the matching index for this timeframe
            current_ts = data[primary_tf][current_idx]['timestamp']

            # Get all candles up to current time
            tf_candles = [c for c in candles if c['timestamp'] <= current_ts]

            if not tf_candles:
                continue

            # Take last N candles (lookback window)
            lookback_map = {
                '1m': 300,
                '5m': 300,
                '15m': 200,
                '1H': 100,
                '4H': 100
            }
            lookback = lookback_map.get(tf_name, 100)
            recent_candles = tf_candles[-lookback:] if len(tf_candles) > lookback else tf_candles

            # Calculate indicators
            indicators = self._calculate_indicators(recent_candles)

            market_state['timeframes'][tf_name] = {
                'candles': recent_candles,
                'current_price': recent_candles[-1]['close'],
                **indicators
            }

        return market_state

    def _calculate_indicators(self, candles: List[Dict]) -> Dict:
        """Calculate technical indicators for candles"""
        if len(candles) < 20:
            return {}

        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        volumes = [c['volume'] for c in candles]

        indicators = {}

        # ATR - calculate_atr returns single float, calculate_atr_series returns list
        atr_series = self.indicators.calculate_atr_series(highs, lows, closes, period=14)
        if atr_series:
            # Calculate ATR percentile for compression check
            atr_percentile = self.indicators.calculate_atr_percentile(atr_series[-1], atr_series)
            is_compressed = self.indicators.is_volatility_compressed(atr_series)
            
            indicators['atr'] = {
                'atr': atr_series[-1],
                'atr_previous': atr_series[-2] if len(atr_series) > 1 else atr_series[-1],
                'atr_series': atr_series,  # Include full series for compression check
                'atr_percentile': atr_percentile,
                'is_compressed': is_compressed
            }

        # Trend
        ema_fast = self.indicators.calculate_ema(closes, period=20)
        ema_slow = self.indicators.calculate_ema(closes, period=50)

        if ema_fast and ema_slow:
            trend_direction = 'up' if ema_fast[-1] > ema_slow[-1] else 'down'
            trend_strength = abs(ema_fast[-1] - ema_slow[-1]) / ema_slow[-1]

            indicators['trend'] = {
                'trend_direction': trend_direction,
                'trend_strength': min(trend_strength * 10, 1.0),  # Normalize to 0-1
                'ema_20': ema_fast[-1],
                'ema_50': ema_slow[-1]
            }

        # Volume
        avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
        indicators['volume'] = {
            'current_volume': volumes[-1],
            'average_volume': avg_volume,
            'volume_ratio': volumes[-1] / avg_volume if avg_volume > 0 else 1.0
        }

        return indicators

    def _check_for_signals(self, sol_market_state: Dict, btc_market_state: Dict,
                          current_time: datetime):
        """
        Check for trading signals from strategies
        """
        # Check daily trade limit
        today_str = current_time.strftime('%Y-%m-%d')
        daily_count = self.daily_trades_count.get(today_str, 0)
        if daily_count >= config.MAX_DAILY_TRADES:
            return

        # Check trade interval
        if self.last_trade_time:
            minutes_since_last = (current_time - self.last_trade_time).total_seconds() / 60
            if minutes_since_last < config.TRADE_INTERVAL_MINUTES:
                return

        # DEBUG: Log what we're checking every 100 candles
        if len(self.trades) % 100 == 0:
            logger.debug(f"🔍 Checking strategies at {current_time.strftime('%Y-%m-%d %H:%M')}")
            if '15m' in sol_market_state.get('timeframes', {}):
                tf_15m = sol_market_state['timeframes']['15m']
                logger.debug(f"   15m price: ${tf_15m.get('current_price', 0):.2f}")
                trend = tf_15m.get('trend', {})
                logger.debug(f"   15m trend: {trend.get('trend_direction', 'unknown')} (strength: {trend.get('trend_strength', 0):.2f})")
            else:
                logger.debug(f"   ⚠️ No 15m timeframe data available")

        # Try breakout strategy
        breakout_signal = self.breakout_strategy.analyze(sol_market_state)
        if breakout_signal:
            logger.info(f"🎯 BREAKOUT SIGNAL FOUND at {current_time.strftime('%Y-%m-%d %H:%M')}")
            self._process_signal(breakout_signal, 'breakout', sol_market_state,
                               btc_market_state, current_time)
            return

        # Try pullback strategy
        pullback_signal = self.pullback_strategy.analyze(sol_market_state)
        if pullback_signal:
            logger.info(f"🎯 PULLBACK SIGNAL FOUND at {current_time.strftime('%Y-%m-%d %H:%M')}")
            self._process_signal(pullback_signal, 'pullback', sol_market_state,
                               btc_market_state, current_time)
            return
        
        # Try trend following strategy EARLY (BACKTEST ONLY - catches trending markets)
        if self.trend_following_strategy:
            tf_signal = self.trend_following_strategy.analyze(sol_market_state)
            if tf_signal:
                logger.info(f"🎯 TREND FOLLOWING SIGNAL FOUND at {current_time.strftime('%Y-%m-%d %H:%M')}")
                self._process_signal(tf_signal, 'trend_following', sol_market_state,
                                   btc_market_state, current_time)
                return
        
        # Try mean reversion strategy (ELITE: with strict regime checking)
        if self.mean_reversion_strategy:
            # ELITE: Check regime before generating signal
            regime_allowed, regime_confidence = self.elite_regime_checker.check(sol_market_state)
            
            if not regime_allowed:
                # Track blocked signals
                if not hasattr(self, 'mr_elite_blocks'):
                    self.mr_elite_blocks = 0
                self.mr_elite_blocks += 1
            else:
                mr_signal = self.mean_reversion_strategy.analyze(sol_market_state)
                if mr_signal:
                    # ELITE: Check for confirmation candle
                    if getattr(config, 'ELITE_BACKTEST_MODE', False) and getattr(config, 'ELITE_REQUIRE_CONFIRMATION', False):
                        candles = sol_market_state.get('timeframes', {}).get('15m', {}).get('candles', [])
                        direction = mr_signal.get('direction', 'long')
                        if not self.elite_confirmation_checker.check_confirmation(candles, direction):
                            self.elite_stats['confirmation_fails'] += 1
                            logger.debug(f"🚫 MR signal needs confirmation - waiting")
                            return
                    
                    # ELITE: Apply adaptive position sizing based on confidence
                    elite_sizing = getattr(config, 'ELITE_ADAPTIVE_SIZING', False)
                    if elite_sizing and getattr(config, 'ELITE_BACKTEST_MODE', False):
                        if regime_confidence >= 0.5:
                            mr_signal['position_size_mult'] = getattr(config, 'ELITE_SIZE_FULL', 1.0)
                            size_label = "FULL"
                        elif regime_confidence >= 0.2:
                            mr_signal['position_size_mult'] = getattr(config, 'ELITE_SIZE_HALF', 0.5)
                            size_label = "HALF"
                        else:
                            mr_signal['position_size_mult'] = getattr(config, 'ELITE_SIZE_SKIP', 0.0)
                            size_label = "SKIP"
                            logger.info(f"🚫 MR signal SKIPPED - very low confidence ({regime_confidence:.2f})")
                            return
                        
                        logger.info(f"🎯 MEAN REVERSION ({size_label}) at {current_time.strftime('%Y-%m-%d %H:%M')} (conf: {regime_confidence:.2f})")
                    else:
                        mr_signal['position_size_mult'] = 1.0
                        logger.info(f"🎯 MEAN REVERSION SIGNAL at {current_time.strftime('%Y-%m-%d %H:%M')}")
                    
                    self._process_signal(mr_signal, 'mean_reversion', sol_market_state,
                                       btc_market_state, current_time)
                    return
        
        # Try momentum strategy
        if self.momentum_strategy:
            momentum_signal = self.momentum_strategy.analyze(sol_market_state)
            if momentum_signal:
                logger.info(f"🎯 MOMENTUM SIGNAL FOUND at {current_time.strftime('%Y-%m-%d %H:%M')}")
                self._process_signal(momentum_signal, 'momentum', sol_market_state,
                                   btc_market_state, current_time)
                return
        
        # Try structure strategy
        if self.structure_strategy:
            structure_signal = self.structure_strategy.analyze(sol_market_state)
            if structure_signal:
                logger.info(f"🎯 STRUCTURE SIGNAL FOUND at {current_time.strftime('%Y-%m-%d %H:%M')}")
                self._process_signal(structure_signal, 'structure', sol_market_state,
                                   btc_market_state, current_time)
                return
        
    def _process_signal(self, signal: Dict, strategy: str,
                       sol_market_state: Dict, btc_market_state: Dict,
                       current_time: datetime):
        """
        Process a trading signal through filters
        """
        self.stats['total_signals'] += 1

        # Normalize direction (LONG/long -> long, SHORT/short -> short)
        direction = signal['direction'].lower()

        # Create trade object
        # Handle key name mismatches: strategy uses stop_loss/take_profit, code expects stop_price/target_price
        # Support V3 multiple TP levels
        trade = BacktestTrade(
            signal_id=f"{strategy}_{current_time.strftime('%Y%m%d_%H%M%S')}",
            timestamp=current_time,
            symbol=config.TRADING_SYMBOL,
            direction=direction,
            strategy=strategy,
            entry_price=signal['entry_price'],
            stop_price=signal.get('stop_price', signal.get('stop_loss')),
            target_price=signal.get('target_price', signal.get('take_profit', signal.get('take_profit_1', signal.get('tp1')))),
            take_profit_1=signal.get('take_profit_1', signal.get('tp1')),
            take_profit_2=signal.get('take_profit_2', signal.get('tp2')),
            take_profit_3=signal.get('take_profit_3', signal.get('tp3')),
            position_split=signal.get('position_split', {1: 0.5, 2: 0.3, 3: 0.2}),
            position_size=0.0  # Will calculate if filters pass
        )

        # Run through filters
        # TF strategy uses looser quality threshold (different signal characteristics)
        original_score_threshold = getattr(config, 'SCORE_THRESHOLD', 50)
        if strategy.lower() in ['trendfollowing', 'trend_following']:
            config.SCORE_THRESHOLD = getattr(config, 'BACKTEST_TF_MIN_SCORE', 35)
        
        filters_passed, filter_results = self.filter_manager.check_all(
            sol_market_state,
            direction,
            strategy,
            btc_market_state
        )
        
        # Restore original threshold
        config.SCORE_THRESHOLD = original_score_threshold

        trade.filter_results = filter_results
        trade.filter_passed = filters_passed

        if filters_passed:
            # SMART MTF BACKTEST: Check multi-timeframe alignment (strategy-aware)
            mtf_approved = True
            if self.use_mtf and self.mtf_checker:
                # Pass strategy name so MTF can use different logic for Mean Reversion vs Trend Following
                mtf_analysis = self.mtf_checker.analyze(sol_market_state, direction, strategy=strategy)
                if not mtf_analysis.allowed:
                    logger.info(f"📊 MTF BLOCKED [{strategy}]: {mtf_analysis.reason} (1H: {mtf_analysis.trend_1h}, 4H: {mtf_analysis.trend_4h})")
                    self.stats['signals_rejected'] += 1
                    trade.filter_passed = False
                    trade.filter_results['mtf_blocked'] = True
                    trade.filter_results['mtf_reason'] = mtf_analysis.reason
                    self.trades.append(trade)
                    return
                else:
                    # Apply MTF confidence to position sizing
                    signal['mtf_confidence'] = mtf_analysis.confidence
                    logger.debug(f"📊 MTF APPROVED [{strategy}]: alignment={mtf_analysis.alignment_score:.2f}, conf={mtf_analysis.confidence:.2f}")
            
            # ML SCORING: Machine learning based trade evaluation
            ml_approved = True
            if self.use_ml_scoring and self.ml_scorer:
                ml_prediction = self.ml_scorer.score_signal(signal, sol_market_state)
                if not ml_prediction.should_trade:
                    logger.info(f"🤖 ML BLOCKED: {ml_prediction.reason} (score: {ml_prediction.score:.2f})")
                    self.stats['signals_rejected'] += 1
                    trade.filter_passed = False
                    trade.filter_results['ml_blocked'] = True
                    trade.filter_results['ml_score'] = ml_prediction.score
                    trade.filter_results['ml_reason'] = ml_prediction.reason
                    self.trades.append(trade)
                    return
                else:
                    # Apply ML confidence to signal
                    signal['ml_score'] = ml_prediction.score
                    signal['ml_confidence'] = ml_prediction.confidence
                    logger.debug(f"🤖 ML APPROVED: score={ml_prediction.score:.2f}, conf={ml_prediction.confidence:.2f}")
            
            # FEAR & GREED: Sentiment-based filtering
            fg_approved = True
            if self.use_fear_greed and self.fear_greed_backtester:
                fg_allowed, fg_multiplier, fg_reason = self.fear_greed_backtester.evaluate_signal(
                    direction, trade.timestamp, strategy
                )
                if not fg_allowed:
                    logger.info(f"😱 F&G BLOCKED: {fg_reason}")
                    self.stats['signals_rejected'] += 1
                    trade.filter_passed = False
                    trade.filter_results['fg_blocked'] = True
                    trade.filter_results['fg_reason'] = fg_reason
                    self.trades.append(trade)
                    return
                else:
                    # Apply F&G confidence multiplier
                    signal['fg_multiplier'] = fg_multiplier
                    if fg_multiplier != 1.0:
                        logger.info(f"😱 F&G: {fg_reason}")
            
            # FAIR AI BACKTEST: Ask AI to evaluate (without future data)
            ai_approved = True
            if self.use_fair_ai and self.fair_ai_evaluator:
                candles = sol_market_state.get('timeframes', {}).get('15m', {}).get('candles', [])
                trend = sol_market_state.get('timeframes', {}).get('15m', {}).get('trend', {})
                indicators = {
                    'rsi': signal.get('rsi', 'N/A'),
                    'trend_direction': trend.get('trend_direction', 'N/A'),
                    'trend_strength': trend.get('trend_strength', 'N/A'),
                    'bb_position': signal.get('bb_position', 'N/A'),
                    'atr': signal.get('atr', 'N/A')
                }
                # Use trade object for normalized prices (signal may have different key names)
                ai_signal = {
                    'direction': trade.direction,
                    'entry_price': trade.entry_price,
                    'stop_price': trade.stop_price,
                    'target_price': trade.target_price,
                    'rsi': signal.get('rsi'),
                    'bb_position': signal.get('bb_position')
                }
                ai_approved, ai_confidence, ai_reasoning = self.fair_ai_evaluator.evaluate_signal(
                    candles, ai_signal, indicators
                )
                if not ai_approved:
                    logger.info(f"🤖 AI REJECTED: {ai_reasoning} (conf: {ai_confidence:.0%})")
                    self.stats['signals_rejected'] += 1
                    trade.filter_passed = False
                    trade.filter_results['ai_rejected'] = True
                    trade.filter_results['ai_reasoning'] = ai_reasoning
                    self.trades.append(trade)
                    return
                else:
                    logger.info(f"🤖 AI APPROVED: {ai_reasoning} (conf: {ai_confidence:.0%})")
            
            self.stats['signals_passed_filters'] += 1
            self._execute_trade(trade, sol_market_state, signal)
        else:
            self.stats['signals_rejected'] += 1
            # Track which filters reject most
            for failed_filter in filter_results.get('failed_filters', []):
                self.stats['filter_rejection_counts'][failed_filter] = \
                    self.stats['filter_rejection_counts'].get(failed_filter, 0) + 1

        # Store trade (even if rejected) for analysis
        self.trades.append(trade)

    def _execute_trade(self, trade: BacktestTrade, market_state: Dict, signal: Dict = None):
        """
        Execute a trade (simulate)
        """
        # Get position size multiplier from filter results (based on score)
        position_multiplier = trade.filter_results.get('position_size_multiplier', 1.0)
        
        # Apply regime-based position sizing if available
        if signal and 'position_size_mult' in signal:
            regime_mult = signal.get('position_size_mult', 1.0)
            position_multiplier *= regime_mult
            if regime_mult < 1.0:
                logger.info(f"   📉 Regime adjustment: {regime_mult:.1f}x position size")
        
        # Calculate position size with multiplier
        base_risk = config.MAX_RISK_PER_TRADE * position_multiplier
        account_risk = self.current_capital * base_risk
        stop_distance = abs(trade.entry_price - trade.stop_price)
        position_size = account_risk / stop_distance if stop_distance > 0 else 0

        if position_size <= 0:
            return

        # Apply slippage (0.02% = 2 basis points)
        slippage_pct = 0.0002
        if trade.direction == 'long':
            actual_entry = trade.entry_price * (1 + slippage_pct)
        else:
            actual_entry = trade.entry_price * (1 - slippage_pct)

        trade.executed = True
        trade.position_size = position_size
        trade.remaining_position = position_size  # Track remaining position for partial exits
        trade.entry_slippage = slippage_pct
        trade.actual_entry_price = actual_entry

        # Set as open position
        self.open_position = trade

        # Update stats
        self.stats['trades_executed'] += 1
        today_str = trade.timestamp.strftime('%Y-%m-%d')
        self.daily_trades_count[today_str] = self.daily_trades_count.get(today_str, 0) + 1
        self.last_trade_time = trade.timestamp

        logger.info(f"📈 TRADE OPENED: {trade.direction.upper()} @ ${trade.actual_entry_price:.2f} "
                   f"(SL: ${trade.stop_price:.2f}, TP: ${trade.target_price:.2f})")

    def _update_open_position(self, candle: Dict, current_time: datetime):
        """
        Update open position and check for exit conditions
        """
        if not self.open_position:
            return

        trade = self.open_position
        current_price = candle['close']
        high = candle['high']
        low = candle['low']

        # Update bars held
        trade.bars_held += 1

        # Update MFE/MAE
        if trade.direction == 'long':
            excursion = (high - trade.actual_entry_price) / trade.actual_entry_price
            adverse = (trade.actual_entry_price - low) / trade.actual_entry_price
        else:
            excursion = (trade.actual_entry_price - low) / trade.actual_entry_price
            adverse = (high - trade.actual_entry_price) / trade.actual_entry_price

        trade.max_favorable_excursion = max(trade.max_favorable_excursion, excursion)
        trade.max_adverse_excursion = max(trade.max_adverse_excursion, adverse)

        # Check exit conditions - Support multiple TP levels (V3)
        exit_triggered = False
        exit_price = None
        exit_reason = None
        
        # Check for partial exits at TP levels (V3 feature)
        if trade.take_profit_1 and trade.take_profit_2 and trade.take_profit_3:
            # V3: Multiple TP levels with position splits
            if trade.direction == 'long':
                # Check stop loss first (closes entire position)
                if low <= trade.stop_price:
                    exit_price = trade.stop_price
                    exit_reason = 'stop'
                    exit_triggered = True
                # Check TP levels in order (partial exits)
                elif not trade.tp1_exited and high >= trade.take_profit_1:
                    exit_price = trade.take_profit_1
                    exit_reason = 'tp1'
                    self._partial_exit(trade, exit_price, 1, current_time)
                elif not trade.tp2_exited and high >= trade.take_profit_2:
                    exit_price = trade.take_profit_2
                    exit_reason = 'tp2'
                    self._partial_exit(trade, exit_price, 2, current_time)
                elif not trade.tp3_exited and high >= trade.take_profit_3:
                    exit_price = trade.take_profit_3
                    exit_reason = 'tp3'
                    self._partial_exit(trade, exit_price, 3, current_time)
            else:  # short
                # Check stop loss first
                if high >= trade.stop_price:
                    exit_price = trade.stop_price
                    exit_reason = 'stop'
                    exit_triggered = True
                # Check TP levels in order
                elif not trade.tp1_exited and low <= trade.take_profit_1:
                    exit_price = trade.take_profit_1
                    exit_reason = 'tp1'
                    self._partial_exit(trade, exit_price, 1, current_time)
                elif not trade.tp2_exited and low <= trade.take_profit_2:
                    exit_price = trade.take_profit_2
                    exit_reason = 'tp2'
                    self._partial_exit(trade, exit_price, 2, current_time)
                elif not trade.tp3_exited and low <= trade.take_profit_3:
                    exit_price = trade.take_profit_3
                    exit_reason = 'tp3'
                    self._partial_exit(trade, exit_price, 3, current_time)
        else:
            # Legacy single TP handling
            if trade.direction == 'long':
                # Check stop loss
                if low <= trade.stop_price:
                    exit_price = trade.stop_price
                    exit_reason = 'stop'
                    exit_triggered = True
                # Check target
                elif high >= trade.target_price:
                    exit_price = trade.target_price
                    exit_reason = 'target'
                    exit_triggered = True
            else:  # short
                # Check stop loss
                if high >= trade.stop_price:
                    exit_price = trade.stop_price
                    exit_reason = 'stop'
                    exit_triggered = True
                # Check target
                elif low <= trade.target_price:
                    exit_price = trade.target_price
                    exit_reason = 'target'
                    exit_triggered = True

        # Timeout after 50 bars (for 15m TF = 12.5 hours) - closes remaining position
        if trade.bars_held >= 50 and trade.remaining_position > 0:
            exit_price = current_price
            exit_reason = 'timeout'
            exit_triggered = True

        if exit_triggered:
            self._close_position(exit_price, exit_reason, current_time)

    def _partial_exit(self, trade: BacktestTrade, exit_price: float, tp_level: int, current_time: datetime):
        """
        Handle partial exit at TP level (V3 feature)
        
        Args:
            trade: The open trade
            exit_price: Price at which to exit
            tp_level: Which TP level (1, 2, or 3)
            current_time: Current timestamp
        """
        if tp_level == 1:
            trade.tp1_exited = True
            split_pct = trade.position_split.get(1, 0.5)
            
            # ELITE: Move stop to breakeven after TP1
            if getattr(config, 'ELITE_BACKTEST_MODE', False) and getattr(config, 'ELITE_BREAKEVEN_AFTER_TP1', False):
                buffer = getattr(config, 'ELITE_BREAKEVEN_BUFFER', 0.001)
                old_stop = trade.stop_price
                if trade.direction == 'long':
                    # Move stop to just below entry (with buffer)
                    new_stop = trade.actual_entry_price * (1 - buffer)
                    if new_stop > old_stop:  # Only move if it's an improvement
                        trade.stop_price = new_stop
                        logger.info(f"   🔒 ELITE: Stop moved to breakeven ${new_stop:.2f} (was ${old_stop:.2f})")
                        self.elite_stats['breakeven_stops'] += 1
                else:
                    # Short: move stop to just above entry
                    new_stop = trade.actual_entry_price * (1 + buffer)
                    if new_stop < old_stop:  # Only move if it's an improvement
                        trade.stop_price = new_stop
                        logger.info(f"   🔒 ELITE: Stop moved to breakeven ${new_stop:.2f} (was ${old_stop:.2f})")
                        self.elite_stats['breakeven_stops'] += 1
                        
        elif tp_level == 2:
            trade.tp2_exited = True
            split_pct = trade.position_split.get(2, 0.3)
        else:  # tp_level == 3
            trade.tp3_exited = True
            split_pct = trade.position_split.get(3, 0.2)
        
        # Calculate position size to exit
        exit_size = trade.position_size * split_pct
        
        # Apply exit slippage
        slippage_pct = 0.0002
        if trade.direction == 'long':
            actual_exit = exit_price * (1 - slippage_pct)
        else:
            actual_exit = exit_price * (1 + slippage_pct)
        
        # Calculate PnL for this partial exit
        if trade.direction == 'long':
            pnl_points = actual_exit - trade.actual_entry_price
        else:
            pnl_points = trade.actual_entry_price - actual_exit
        
        pnl_dollar = pnl_points * exit_size
        
        # Update trade
        trade.remaining_position -= exit_size
        trade.partial_exits_pnl += pnl_dollar
        
        # Update capital
        self.current_capital += pnl_dollar
        
        logger.info(f"💰 PARTIAL EXIT TP{tp_level}: {exit_size:.2f} contracts @ ${actual_exit:.2f} | "
                   f"PnL: ${pnl_dollar:+.2f} | Remaining: {trade.remaining_position:.2f}")
        
        # If all position exited, close trade
        if trade.remaining_position <= 0.001:  # Small threshold for floating point
            self._close_position(actual_exit, f'tp{tp_level}_complete', current_time)

    def _close_position(self, exit_price: float, exit_reason: str, current_time: datetime):
        """
        Close the open position
        """
        if not self.open_position:
            return

        trade = self.open_position

        # Apply exit slippage
        slippage_pct = 0.0002
        if trade.direction == 'long':
            actual_exit = exit_price * (1 - slippage_pct)
        else:
            actual_exit = exit_price * (1 + slippage_pct)

        trade.exit_timestamp = current_time
        trade.exit_price = actual_exit
        trade.exit_reason = exit_reason

        # Calculate PnL
        # For V3 trades with partial exits, use remaining position
        # For legacy trades, use full position
        position_to_close = trade.remaining_position if trade.remaining_position > 0 else trade.position_size
        
        if trade.direction == 'long':
            pnl_points = actual_exit - trade.actual_entry_price
        else:
            pnl_points = trade.actual_entry_price - actual_exit

        pnl_percent = pnl_points / trade.actual_entry_price
        pnl_dollar = pnl_points * position_to_close
        
        # Add partial exits PnL if any
        if trade.partial_exits_pnl != 0:
            pnl_dollar += trade.partial_exits_pnl

        trade.pnl_points = pnl_points
        trade.pnl_percent = pnl_percent
        trade.pnl_dollar = pnl_dollar
        trade.win = pnl_dollar > 0

        # Update capital
        self.current_capital += pnl_dollar
        self.stats['total_pnl'] += pnl_dollar

        # Update drawdown
        if self.current_capital > self.stats['peak_capital']:
            self.stats['peak_capital'] = self.current_capital
        drawdown = (self.stats['peak_capital'] - self.current_capital) / self.stats['peak_capital']
        self.stats['max_drawdown'] = max(self.stats['max_drawdown'], drawdown)

        # Update win/loss stats
        if pnl_dollar > trade.actual_entry_price * 0.001:  # Win if >0.1% profit
            self.stats['wins'] += 1
        elif pnl_dollar < -trade.actual_entry_price * 0.001:  # Loss if >0.1% loss
            self.stats['losses'] += 1
        else:
            self.stats['breakevens'] += 1

        # Calculate R:R
        risk = abs(trade.actual_entry_price - trade.stop_price)
        actual_reward = abs(pnl_points)
        trade.risk_reward_achieved = actual_reward / risk if risk > 0 else 0

        # Log
        result_emoji = "✅" if trade.win else "❌"
        logger.info(f"{result_emoji} TRADE CLOSED: {exit_reason.upper()} @ ${actual_exit:.2f} | "
                   f"PnL: ${pnl_dollar:+.2f} ({pnl_percent*100:+.2f}%) | "
                   f"Held: {trade.bars_held} bars")

        # Clear open position
        self.open_position = None

    def _force_close_position(self, final_candle: Dict, reason: str):
        """Force close position at end of backtest"""
        if self.open_position:
            current_time = datetime.fromtimestamp(final_candle['timestamp'] / 1000)
            self._close_position(final_candle['close'], reason, current_time)

    def _generate_results(self) -> Dict:
        """
        Generate comprehensive backtest results
        """
        executed_trades = [t for t in self.trades if t.executed]
        wins = [t for t in executed_trades if t.win]
        losses = [t for t in executed_trades if not t.win and t.pnl_dollar < 0]

        results = {
            'summary': {
                'initial_capital': self.initial_capital,
                'final_capital': self.current_capital,
                'total_pnl': self.stats['total_pnl'],
                'total_return_pct': (self.current_capital - self.initial_capital) / self.initial_capital * 100,
                'max_drawdown_pct': self.stats['max_drawdown'] * 100,
                'requested_start_date': self.start_date,
                'requested_end_date': self.end_date,
                'actual_start_date': getattr(self, 'actual_start_date', self.start_date),
                'actual_end_date': getattr(self, 'actual_end_date', self.end_date),
            },
            'signals': {
                'total_signals': self.stats['total_signals'],
                'signals_passed_filters': self.stats['signals_passed_filters'],
                'signals_rejected': self.stats['signals_rejected'],
                'filter_pass_rate': (self.stats['signals_passed_filters'] / self.stats['total_signals'] * 100)
                    if self.stats['total_signals'] > 0 else 0
            },
            'trades': {
                'total_trades': len(executed_trades),
                'wins': len(wins),
                'losses': len(losses),
                'breakevens': self.stats['breakevens'],
                'win_rate': (len(wins) / len(executed_trades) * 100) if executed_trades else 0,
            },
            'performance': {},
            'filter_rejections': self.stats['filter_rejection_counts'],
            'all_trades': self.trades
        }

        # Calculate performance metrics
        if wins:
            results['performance']['avg_win'] = sum(t.pnl_dollar for t in wins) / len(wins)
            results['performance']['avg_win_pct'] = sum(t.pnl_percent for t in wins) / len(wins) * 100
            results['performance']['largest_win'] = max(t.pnl_dollar for t in wins)

        if losses:
            results['performance']['avg_loss'] = sum(t.pnl_dollar for t in losses) / len(losses)
            results['performance']['avg_loss_pct'] = sum(t.pnl_percent for t in losses) / len(losses) * 100
            results['performance']['largest_loss'] = min(t.pnl_dollar for t in losses)

        if wins and losses:
            results['performance']['profit_factor'] = abs(sum(t.pnl_dollar for t in wins) /
                                                         sum(t.pnl_dollar for t in losses))

        return results
