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
from strategy.pullback_strategy import PullbackStrategy
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
    target_price: float
    position_size: float  # Number of contracts

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
    exit_reason: Optional[str] = None  # 'target', 'stop', 'timeout'
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


class BacktestEngine:
    """
    Comprehensive backtesting engine

    Simulates trading system performance on historical data
    """

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # Initialize components
        self.breakout_strategy = BreakoutStrategyV2()  # Use improved v2 strategy
        self.pullback_strategy = PullbackStrategy()
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
        trade = BacktestTrade(
            signal_id=f"{strategy}_{current_time.strftime('%Y%m%d_%H%M%S')}",
            timestamp=current_time,
            symbol=config.TRADING_SYMBOL,
            direction=direction,
            strategy=strategy,
            entry_price=signal['entry_price'],
            stop_price=signal.get('stop_price', signal.get('stop_loss')),
            target_price=signal.get('target_price', signal.get('take_profit', signal.get('take_profit_1', signal.get('tp1')))),
            position_size=0.0  # Will calculate if filters pass
        )

        # Run through filters
        filters_passed, filter_results = self.filter_manager.check_all(
            sol_market_state,
            direction,
            strategy,
            btc_market_state
        )

        trade.filter_results = filter_results
        trade.filter_passed = filters_passed

        if filters_passed:
            self.stats['signals_passed_filters'] += 1
            self._execute_trade(trade, sol_market_state)
        else:
            self.stats['signals_rejected'] += 1
            # Track which filters reject most
            for failed_filter in filter_results.get('failed_filters', []):
                self.stats['filter_rejection_counts'][failed_filter] = \
                    self.stats['filter_rejection_counts'].get(failed_filter, 0) + 1

        # Store trade (even if rejected) for analysis
        self.trades.append(trade)

    def _execute_trade(self, trade: BacktestTrade, market_state: Dict):
        """
        Execute a trade (simulate)
        """
        # Get position size multiplier from filter results (based on score)
        position_multiplier = trade.filter_results.get('position_size_multiplier', 1.0)
        
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

        # Check exit conditions
        exit_triggered = False
        exit_price = None
        exit_reason = None

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

        # Timeout after 50 bars (for 15m TF = 12.5 hours)
        if trade.bars_held >= 50:
            exit_price = current_price
            exit_reason = 'timeout'
            exit_triggered = True

        if exit_triggered:
            self._close_position(exit_price, exit_reason, current_time)

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
        if trade.direction == 'long':
            pnl_points = actual_exit - trade.actual_entry_price
        else:
            pnl_points = trade.actual_entry_price - actual_exit

        pnl_percent = pnl_points / trade.actual_entry_price
        pnl_dollar = pnl_points * trade.position_size

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
