"""
Pattern Failure Filter
Detects and rejects common trap patterns:
- Bull traps
- Bear traps
- Stop hunts
- Fakeouts
- Low liquidity spikes
"""

from typing import Dict, Tuple, List, Optional
import numpy as np
import logging
from config import (
    BULL_TRAP_THRESHOLD,
    BEAR_TRAP_THRESHOLD,
    LOW_LIQUIDITY_VOLUME_RATIO,
    STOP_HUNT_WICK_RATIO,
    FAKEOUT_REVERSION_PCT
)

logger = logging.getLogger(__name__)


class PatternFailureFilter:
    """
    Filter #4: Pattern Failure Detection
    Identifies and rejects trap patterns and fakeouts
    """

    def __init__(self):
        self.name = "PatternFailure"
        self.recent_patterns = []  # Track recent patterns detected

    def check(self, market_state: Dict, signal_direction: str) -> Tuple[bool, str]:
        """
        Check for trap patterns that invalidate the setup

        Args:
            market_state: Complete market state
            signal_direction: 'long' or 'short'

        Returns:
            (passed: bool, reason: str)
        """
        try:
            timeframes = market_state.get('timeframes', {})

            # Use 5m timeframe for pattern detection (sensitive to traps)
            primary_tf = '5m'
            if primary_tf not in timeframes:
                primary_tf = LTF_TIMEFRAME if 'LTF_TIMEFRAME' in globals() else '15m'

            if primary_tf not in timeframes:
                logger.warning(f"{self.name}: No suitable timeframe for pattern detection")
                return True, "No pattern data (allowed)"

            tf_data = timeframes[primary_tf]
            candles = tf_data.get('candles', [])

            if len(candles) < 10:
                return True, "Insufficient candle data"

            # Check 1: Bull/Bear Trap Detection
            trap_check = self._detect_trap(candles, signal_direction)
            if not trap_check[0]:
                return trap_check

            # Check 2: Stop Hunt Detection
            stop_hunt_check = self._detect_stop_hunt(candles, signal_direction)
            if not stop_hunt_check[0]:
                return stop_hunt_check

            # Check 3: Fakeout Detection
            fakeout_check = self._detect_fakeout(candles, signal_direction)
            if not fakeout_check[0]:
                return fakeout_check

            # Check 4: Low Liquidity Spike Detection
            liquidity_check = self._detect_low_liquidity_spike(candles, tf_data)
            if not liquidity_check[0]:
                return liquidity_check

            # All checks passed
            logger.info(f"✅ {self.name}: No trap patterns detected")
            return True, "No trap patterns"

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during filter check: {e}")
            return False, f"Filter error: {e}"

    def _detect_trap(self, candles: List[Dict], signal_direction: str) -> Tuple[bool, str]:
        """
        Detect bull/bear traps

        Bull trap: Price breaks above resistance then quickly reverses
        Bear trap: Price breaks below support then quickly reverses
        """
        if len(candles) < 5:
            return True, "Not enough data"

        recent_candles = candles[-5:]

        # Calculate recent price movement
        highs = [c['high'] for c in recent_candles]
        lows = [c['low'] for c in recent_candles]
        closes = [c['close'] for c in recent_candles]

        highest = max(highs)
        lowest = min(lows)
        current_close = closes[-1]
        price_range = highest - lowest

        if price_range == 0:
            return True, "No price range"

        # Bull trap detection (for long signals)
        if signal_direction == 'long':
            # Check if price spiked up then reversed sharply
            if highs[-2] == highest:  # Recent high
                # If current price dropped significantly from that high
                drop_from_high = (highest - current_close) / price_range
                if drop_from_high > BULL_TRAP_THRESHOLD:
                    self._log_pattern("Bull Trap", signal_direction)
                    return False, f"Bull trap detected (dropped {drop_from_high*100:.1f}% from high)"

        # Bear trap detection (for short signals)
        elif signal_direction == 'short':
            # Check if price spiked down then reversed sharply
            if lows[-2] == lowest:  # Recent low
                # If current price rallied significantly from that low
                rally_from_low = (current_close - lowest) / price_range
                if rally_from_low > BEAR_TRAP_THRESHOLD:
                    self._log_pattern("Bear Trap", signal_direction)
                    return False, f"Bear trap detected (rallied {rally_from_low*100:.1f}% from low)"

        return True, "No traps detected"

    def _detect_stop_hunt(self, candles: List[Dict], signal_direction: str) -> Tuple[bool, str]:
        """
        Detect stop hunts (large wicks indicating liquidity grabs)

        Stop hunt characteristics:
        - Large wick relative to body
        - Quick reversal
        - Often at key levels
        """
        if len(candles) < 3:
            return True, "Not enough data"

        recent_candles = candles[-3:]

        for i, candle in enumerate(recent_candles):
            open_price = candle['open']
            close_price = candle['close']
            high = candle['high']
            low = candle['low']

            # Calculate body and wick sizes
            body_size = abs(close_price - open_price)
            if body_size == 0:
                body_size = 0.0001  # Avoid division by zero

            # Upper and lower wicks
            upper_wick = high - max(open_price, close_price)
            lower_wick = min(open_price, close_price) - low

            # For long signals, check for downside stop hunt
            if signal_direction == 'long':
                lower_wick_ratio = lower_wick / body_size
                if lower_wick_ratio > STOP_HUNT_WICK_RATIO:
                    # Check if price recovered
                    if close_price > open_price:  # Closed higher after the hunt
                        # This might actually be a good sign (cleared stops)
                        logger.info(f"{self.name}: Downside stop hunt cleared (bullish)")
                    else:
                        self._log_pattern("Stop Hunt (Long)", signal_direction)
                        return False, f"Stop hunt detected (lower wick {lower_wick_ratio:.1f}x body)"

            # For short signals, check for upside stop hunt
            elif signal_direction == 'short':
                upper_wick_ratio = upper_wick / body_size
                if upper_wick_ratio > STOP_HUNT_WICK_RATIO:
                    # Check if price recovered
                    if close_price < open_price:  # Closed lower after the hunt
                        # This might actually be a good sign
                        logger.info(f"{self.name}: Upside stop hunt cleared (bearish)")
                    else:
                        self._log_pattern("Stop Hunt (Short)", signal_direction)
                        return False, f"Stop hunt detected (upper wick {upper_wick_ratio:.1f}x body)"

        return True, "No stop hunts detected"

    def _detect_fakeout(self, candles: List[Dict], signal_direction: str) -> Tuple[bool, str]:
        """
        Detect fakeout breakouts

        Fakeout: Price breaks a level but quickly reverts
        """
        if len(candles) < 10:
            return True, "Not enough data"

        recent_candles = candles[-10:]
        earlier_candles = candles[-20:-10] if len(candles) >= 20 else candles[:-10]

        if not earlier_candles:
            return True, "Not enough historical data"

        # Calculate support/resistance from earlier period
        earlier_highs = [c['high'] for c in earlier_candles]
        earlier_lows = [c['low'] for c in earlier_candles]

        resistance = max(earlier_highs)
        support = min(earlier_lows)

        # Check recent candles for fakeout
        for i in range(len(recent_candles) - 3):
            candle = recent_candles[i]
            following_candles = recent_candles[i+1:i+4]

            # For long signals: check for fakeout above resistance
            if signal_direction == 'long':
                # Did price break above resistance?
                if candle['high'] > resistance:
                    # Did it quickly reverse back below?
                    avg_close_after = np.mean([c['close'] for c in following_candles])
                    reversion = (candle['high'] - avg_close_after) / (candle['high'] - resistance) if candle['high'] != resistance else 0

                    if reversion > FAKEOUT_REVERSION_PCT:
                        self._log_pattern("Fakeout Breakout (Long)", signal_direction)
                        return False, f"Fakeout above resistance detected ({reversion*100:.1f}% reversion)"

            # For short signals: check for fakeout below support
            elif signal_direction == 'short':
                # Did price break below support?
                if candle['low'] < support:
                    # Did it quickly reverse back above?
                    avg_close_after = np.mean([c['close'] for c in following_candles])
                    reversion = (avg_close_after - candle['low']) / (support - candle['low']) if support != candle['low'] else 0

                    if reversion > FAKEOUT_REVERSION_PCT:
                        self._log_pattern("Fakeout Breakdown (Short)", signal_direction)
                        return False, f"Fakeout below support detected ({reversion*100:.1f}% reversion)"

        return True, "No fakeouts detected"

    def _detect_low_liquidity_spike(self, candles: List[Dict], tf_data: Dict) -> Tuple[bool, str]:
        """
        Detect price spikes on abnormally low volume
        These are often unreliable and should be avoided
        """
        if len(candles) < 10:
            return True, "Not enough data"

        volume_data = tf_data.get('volume', {})
        if not volume_data:
            return True, "No volume data"

        current_volume_ratio = volume_data.get('volume_ratio', 1.0)

        # Check if current candle has large price movement but low volume
        recent_candles = candles[-5:]
        price_changes = []

        for i in range(1, len(recent_candles)):
            prev_close = recent_candles[i-1]['close']
            curr_close = recent_candles[i]['close']
            change = abs(curr_close - prev_close) / prev_close
            price_changes.append(change)

        avg_price_change = np.mean(price_changes)
        latest_change = price_changes[-1]

        # Large price move (>1.5x average) on low volume (<30% of average)
        if latest_change > avg_price_change * 1.5 and current_volume_ratio < LOW_LIQUIDITY_VOLUME_RATIO:
            self._log_pattern("Low Liquidity Spike", "")
            return False, f"Low liquidity spike detected (volume {current_volume_ratio*100:.0f}% of avg)"

        return True, "Liquidity OK"

    def _log_pattern(self, pattern_name: str, signal_direction: str):
        """Log detected pattern for analysis"""
        self.recent_patterns.append({
            'pattern': pattern_name,
            'direction': signal_direction,
            'timestamp': None  # Would add timestamp in production
        })

        # Keep only recent patterns
        if len(self.recent_patterns) > 50:
            self.recent_patterns = self.recent_patterns[-50:]

        logger.warning(f"⚠️  {self.name}: {pattern_name} detected for {signal_direction} signal")

    def get_recent_patterns(self) -> List[Dict]:
        """Get recently detected patterns for analysis"""
        return self.recent_patterns.copy()

    def get_pattern_statistics(self) -> Dict:
        """Get statistics on detected patterns"""
        if not self.recent_patterns:
            return {'total': 0}

        pattern_counts = {}
        for p in self.recent_patterns:
            pattern_name = p['pattern']
            pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + 1

        return {
            'total': len(self.recent_patterns),
            'by_type': pattern_counts
        }
