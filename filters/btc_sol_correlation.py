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
        Check if BTC and SOL are properly correlated

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
            # Check 1: Trend Agreement (BTC and SOL trending same direction)
            if BTC_SOL_TREND_AGREEMENT_REQUIRED:
                trend_check = self._check_trend_agreement(
                    sol_market_state,
                    btc_market_state,
                    signal_direction
                )
                if not trend_check[0]:
                    return trend_check

            # Check 2: Price Correlation
            correlation_check = self._check_price_correlation(
                sol_market_state,
                btc_market_state
            )
            if not correlation_check[0]:
                return correlation_check

            # Check 3: Momentum Alignment
            momentum_check = self._check_momentum_alignment(
                sol_market_state,
                btc_market_state,
                signal_direction
            )
            if not momentum_check[0]:
                return momentum_check

            logger.info(f"✅ {self.name}: BTC-SOL correlation healthy")
            return True, "BTC-SOL correlation confirmed"

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during filter check: {e}")
            return False, f"Filter error: {e}"

    def _check_trend_agreement(self, sol_state: Dict, btc_state: Dict,
                               signal_direction: str) -> Tuple[bool, str]:
        """
        Check if BTC and SOL are trending in the same direction
        """
        sol_timeframes = sol_state.get('timeframes', {})
        btc_timeframes = btc_state.get('timeframes', {})

        # Check HTF (4H) trends
        if '4H' not in sol_timeframes or '4H' not in btc_timeframes:
            # Fall back to 1H if 4H not available
            timeframe = '1H' if '1H' in sol_timeframes and '1H' in btc_timeframes else '15m'
        else:
            timeframe = '4H'

        if timeframe not in sol_timeframes or timeframe not in btc_timeframes:
            return True, "Insufficient timeframe data for comparison"

        sol_trend = sol_timeframes[timeframe].get('trend', {})
        btc_trend = btc_timeframes[timeframe].get('trend', {})

        sol_direction = sol_trend.get('trend_direction', 'sideways')
        btc_direction = btc_trend.get('trend_direction', 'sideways')

        # BTC must be trending in the same direction as our signal
        if signal_direction == 'long' and btc_direction != 'up':
            return False, f"BTC not bullish (BTC: {btc_direction}, signal: {signal_direction})"

        if signal_direction == 'short' and btc_direction != 'down':
            return False, f"BTC not bearish (BTC: {btc_direction}, signal: {signal_direction})"

        # SOL should also align
        if signal_direction == 'long' and sol_direction == 'down':
            return False, f"SOL bearish while BTC bullish (divergence)"

        if signal_direction == 'short' and sol_direction == 'up':
            return False, f"SOL bullish while BTC bearish (divergence)"

        return True, f"BTC and SOL trends aligned ({btc_direction})"

    def _check_price_correlation(self, sol_state: Dict, btc_state: Dict) -> Tuple[bool, str]:
        """
        Calculate price correlation between BTC and SOL
        Uses recent price changes to measure correlation
        """
        sol_timeframes = sol_state.get('timeframes', {})
        btc_timeframes = btc_state.get('timeframes', {})

        # Use 1H timeframe for correlation
        timeframe = '1H' if '1H' in sol_timeframes and '1H' in btc_timeframes else '15m'

        if timeframe not in sol_timeframes or timeframe not in btc_timeframes:
            return True, "Insufficient data for correlation"

        sol_candles = sol_timeframes[timeframe].get('candles', [])
        btc_candles = btc_timeframes[timeframe].get('candles', [])

        if len(sol_candles) < 20 or len(btc_candles) < 20:
            return True, "Not enough candles for correlation"

        # Get recent 20 candles
        sol_recent = sol_candles[-20:]
        btc_recent = btc_candles[-20:]

        # Calculate price changes
        sol_changes = []
        btc_changes = []

        for i in range(1, len(sol_recent)):
            sol_change = (sol_recent[i]['close'] - sol_recent[i-1]['close']) / sol_recent[i-1]['close']
            btc_change = (btc_recent[i]['close'] - btc_recent[i-1]['close']) / btc_recent[i-1]['close']

            sol_changes.append(sol_change)
            btc_changes.append(btc_change)

        # Calculate correlation
        correlation = np.corrcoef(sol_changes, btc_changes)[0, 1]

        if np.isnan(correlation):
            return True, "Unable to calculate correlation"

        if abs(correlation) < BTC_SOL_MIN_CORRELATION:
            return False, f"Low BTC-SOL correlation ({correlation:.2f} < {BTC_SOL_MIN_CORRELATION})"

        return True, f"BTC-SOL correlation strong ({correlation:.2f})"

    def _check_momentum_alignment(self, sol_state: Dict, btc_state: Dict,
                                  signal_direction: str) -> Tuple[bool, str]:
        """
        Check if BTC and SOL momentum are aligned
        """
        sol_timeframes = sol_state.get('timeframes', {})
        btc_timeframes = btc_state.get('timeframes', {})

        # Use 15m for momentum check
        if '15m' not in sol_timeframes or '15m' not in btc_timeframes:
            return True, "Insufficient timeframe data for momentum"

        sol_trend = sol_timeframes['15m'].get('trend', {})
        btc_trend = btc_timeframes['15m'].get('trend', {})

        sol_rsi = sol_trend.get('rsi', 50)
        btc_rsi = btc_trend.get('rsi', 50)

        # For long signals: both should not be oversold or diverging
        if signal_direction == 'long':
            if btc_rsi < 30:
                return False, f"BTC oversold (RSI: {btc_rsi:.1f})"

            # If BTC is strong but SOL is weak, wait
            if btc_rsi > 60 and sol_rsi < 40:
                return False, f"BTC strong but SOL weak (BTC RSI: {btc_rsi:.1f}, SOL RSI: {sol_rsi:.1f})"

        # For short signals: both should not be overbought or diverging
        elif signal_direction == 'short':
            if btc_rsi > 70:
                return False, f"BTC overbought (RSI: {btc_rsi:.1f})"

            # If BTC is weak but SOL is strong, wait
            if btc_rsi < 40 and sol_rsi > 60:
                return False, f"BTC weak but SOL strong (BTC RSI: {btc_rsi:.1f}, SOL RSI: {sol_rsi:.1f})"

        return True, f"BTC-SOL momentum aligned (BTC RSI: {btc_rsi:.1f}, SOL RSI: {sol_rsi:.1f})"

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
