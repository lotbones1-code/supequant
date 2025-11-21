"""
BTC-SOL Correlation Filter
Ensures BTC and SOL are aligned before trading SOL
BTC leads the market, SOL follows - this filter validates the relationship
"""

from typing import Dict, Optional, Tuple
import numpy as np
import logging
from config import (
    BTC_SOL_CORRELATION_ENABLED,
    BTC_SOL_MIN_CORRELATION,
    BTC_SOL_TREND_AGREEMENT_REQUIRED,
    BTC_SOL_DIVERGENCE_MAX,
    REFERENCE_SYMBOL
)

logger = logging.getLogger(__name__)


class BTCSOLCorrelationFilter:
    """
    Filter #5: BTC-SOL Correlation
    Validates that Bitcoin and Solana are moving in harmony
    BTC leads, SOL follows - this ensures the relationship is healthy
    """

    def __init__(self):
        self.name = "BTC-SOL-Correlation"

    def check(self, sol_market_state: Dict, btc_market_state: Dict,
             signal_direction: str) -> Tuple[bool, str]:
        """
        Check if BTC and SOL relationship allows trading

        NEW LOGIC (Less Strict):
        - Only reject on STRONG OPPOSING BTC trends
        - Reject on extreme BTC volatility
        - Allow neutral/sideways BTC
        - Correlation is advisory, not blocking

        Args:
            sol_market_state: Solana market state
            btc_market_state: Bitcoin market state
            signal_direction: 'long' or 'short'

        Returns:
            (passed: bool, reason: str)
        """
        if not BTC_SOL_CORRELATION_ENABLED:
            return True, "Correlation filter disabled"

        try:
            # Check 1: HARD GATE - Strong Opposing BTC Trend
            # Only reject if BTC is STRONGLY moving against our signal
            opposing_check = self._check_strong_opposition(
                btc_market_state,
                signal_direction
            )
            if not opposing_check[0]:
                return opposing_check

            # Check 2: HARD GATE - Extreme BTC Volatility
            # Reject if BTC is going crazy (unsafe conditions)
            volatility_check = self._check_btc_volatility_extreme(
                btc_market_state
            )
            if not volatility_check[0]:
                return volatility_check

            # Check 3: SOFT WARNING - Divergence Detection
            # Log warning but don't block trade
            divergence_check = self._check_dangerous_divergence(
                sol_market_state,
                btc_market_state,
                signal_direction
            )
            if not divergence_check[0]:
                logger.warning(f"⚠️  {self.name}: {divergence_check[1]} (allowing trade)")

            logger.info(f"✅ {self.name}: BTC conditions acceptable for SOL trade")
            return True, "BTC not opposing SOL trade"

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during filter check: {e}")
            # Fail open (allow trade) on errors in this filter
            logger.warning(f"⚠️  {self.name}: Error occurred, allowing trade as fallback")
            return True, f"Filter error (allowed): {e}"

    def _check_strong_opposition(self, btc_state: Dict, signal_direction: str) -> Tuple[bool, str]:
        """
        NEW: Only reject if BTC is STRONGLY opposing the trade direction

        Allows:
        - Neutral/sideways BTC
        - Weak trends
        - Mixed signals

        Rejects ONLY:
        - Strong downtrend on 1H+4H when going long
        - Strong uptrend on 1H+4H when going short
        """
        btc_timeframes = btc_state.get('timeframes', {})

        # Check 1H and 4H trends
        h1_trend = btc_timeframes.get('1H', {}).get('trend', {})
        h4_trend = btc_timeframes.get('4H', {}).get('trend', {})

        if not h1_trend or not h4_trend:
            # Can't determine, allow trade
            return True, "BTC trend data insufficient (allowing)"

        h1_direction = h1_trend.get('trend_direction', 'sideways')
        h1_strength = h1_trend.get('trend_strength', 0)
        h4_direction = h4_trend.get('trend_direction', 'sideways')
        h4_strength = h4_trend.get('trend_strength', 0)

        # For LONG signals: Only reject if BTC STRONGLY bearish
        if signal_direction == 'long':
            # Both 1H and 4H must be down AND strong
            if (h1_direction == 'down' and h1_strength > 0.6 and
                h4_direction == 'down' and h4_strength > 0.6):
                return False, f"BTC strongly bearish (1H: {h1_strength:.2f}, 4H: {h4_strength:.2f})"

        # For SHORT signals: Only reject if BTC STRONGLY bullish
        elif signal_direction == 'short':
            # Both 1H and 4H must be up AND strong
            if (h1_direction == 'up' and h1_strength > 0.6 and
                h4_direction == 'up' and h4_strength > 0.6):
                return False, f"BTC strongly bullish (1H: {h1_strength:.2f}, 4H: {h4_strength:.2f})"

        # BTC not strongly opposing - allow trade
        return True, f"BTC not strongly opposing (1H: {h1_direction}, 4H: {h4_direction})"

    def _check_btc_volatility_extreme(self, btc_state: Dict) -> Tuple[bool, str]:
        """
        NEW: Reject if BTC volatility is extreme (unsafe conditions)

        Checks for:
        - Huge ATR spikes (volatility explosion)
        - Large wicks (stop hunts)
        - Unusual short-term volatility on 1m/5m
        """
        btc_timeframes = btc_state.get('timeframes', {})

        # Check 1: ATR percentile (if in extreme territory)
        if '15m' in btc_timeframes:
            atr_data = btc_timeframes['15m'].get('atr', {})
            atr_percentile = atr_data.get('atr_percentile', 50)

            # If BTC ATR > 95th percentile = extreme volatility
            if atr_percentile > 95:
                return False, f"BTC volatility extreme (ATR {atr_percentile}th percentile)"

        # Check 2: Recent wick sizes (stop hunts)
        if '5m' in btc_timeframes:
            candles = btc_timeframes['5m'].get('candles', [])
            if len(candles) >= 5:
                recent = candles[-5:]
                for candle in recent:
                    body = abs(candle['close'] - candle['open'])
                    upper_wick = candle['high'] - max(candle['close'], candle['open'])
                    lower_wick = min(candle['close'], candle['open']) - candle['low']

                    if body > 0:
                        if upper_wick / body > 4 or lower_wick / body > 4:
                            return False, f"BTC stop hunt detected (large wicks)"

        # Volatility acceptable
        return True, "BTC volatility acceptable"

    def _check_dangerous_divergence(self, sol_state: Dict, btc_state: Dict,
                                    signal_direction: str) -> Tuple[bool, str]:
        """
        NEW: Soft warning for dangerous divergences
        Returns False + reason for logging, but doesn't block trade

        Detects:
        - SOL pumping while BTC nuking (unstable)
        - Extreme opposite movements
        """
        sol_timeframes = sol_state.get('timeframes', {})
        btc_timeframes = btc_state.get('timeframes', {})

        # Check recent price action
        if '15m' not in sol_timeframes or '15m' not in btc_timeframes:
            return True, "No divergence data"

        sol_candles = sol_timeframes['15m'].get('candles', [])
        btc_candles = btc_timeframes['15m'].get('candles', [])

        if len(sol_candles) < 5 or len(btc_candles) < 5:
            return True, "Not enough data for divergence check"

        # Calculate recent moves (last 5 candles)
        sol_move = (sol_candles[-1]['close'] - sol_candles[-5]['close']) / sol_candles[-5]['close']
        btc_move = (btc_candles[-1]['close'] - btc_candles[-5]['close']) / btc_candles[-5]['close']

        # For LONG: Warn if SOL pumping but BTC dumping hard
        if signal_direction == 'long':
            if sol_move > 0.02 and btc_move < -0.02:  # SOL +2%, BTC -2%
                return False, f"SOL pumping (+{sol_move*100:.1f}%) while BTC dumping ({btc_move*100:.1f}%)"

        # For SHORT: Warn if SOL dumping but BTC pumping hard
        elif signal_direction == 'short':
            if sol_move < -0.02 and btc_move > 0.02:  # SOL -2%, BTC +2%
                return False, f"SOL dumping ({sol_move*100:.1f}%) while BTC pumping (+{btc_move*100:.1f}%)"

        return True, "No dangerous divergence"

    def get_correlation_score(self, sol_state: Dict, btc_state: Dict) -> float:
        """
        Calculate overall BTC-SOL correlation score (0-1)

        Returns:
            Score where 1.0 = perfect correlation
        """
        score = 0.0
        checks = 0

        # Trend agreement
        for direction in ['long', 'short']:
            trend_check = self._check_trend_agreement(sol_state, btc_state, direction)
            if trend_check[0]:
                score += 1
                break
        checks += 1

        # Price correlation
        corr_check = self._check_price_correlation(sol_state, btc_state)
        if corr_check[0]:
            score += 1
        checks += 1

        # Momentum alignment
        for direction in ['long', 'short']:
            mom_check = self._check_momentum_alignment(sol_state, btc_state, direction)
            if mom_check[0]:
                score += 1
                break
        checks += 1

        return score / checks if checks > 0 else 0
