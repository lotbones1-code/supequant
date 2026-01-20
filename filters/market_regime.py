"""
Market Regime Filter
Ensures we only trade in favorable market conditions
Checks: volatility, ATR compression, funding rates, open interest
"""

from typing import Dict, Optional, Tuple
import logging
from config import (
    ATR_MIN_PERCENTILE,
    ATR_MAX_PERCENTILE,
    VOLATILITY_COMPRESSION_THRESHOLD,
    FUNDING_RATE_MAX,
    FUNDING_RATE_MIN,
    OI_CHANGE_MAX
)

logger = logging.getLogger(__name__)


class MarketRegimeFilter:
    """
    Filter #1: Market Regime
    Only allow trades when market conditions are stable and favorable
    """

    def __init__(self):
        self.name = "MarketRegime"
        self.last_oi = None  # Track OI changes

    def check(self, market_state: Dict) -> Tuple[bool, str]:
        """
        Check if current market regime is suitable for trading

        Args:
            market_state: Complete market state from MarketDataFeed

        Returns:
            (passed: bool, reason: str)
        """
        try:
            # Check 1: ATR Volatility must be in acceptable range
            atr_check = self._check_atr_volatility(market_state)
            if not atr_check[0]:
                return atr_check

            # Check 2: Funding rate must not be extreme
            funding_check = self._check_funding_rate(market_state)
            if not funding_check[0]:
                return funding_check

            # Check 3: Open Interest should be stable (no extreme changes)
            oi_check = self._check_open_interest(market_state)
            if not oi_check[0]:
                return oi_check

            # Check 4: Look for volatility compression (ideal for breakouts)
            compression_check = self._check_compression_for_breakout(market_state)
            # Note: compression is preferred but not required
            if compression_check[0]:
                logger.info(f"✅ {self.name}: Volatility compression detected (ideal conditions)")

            # All checks passed
            logger.info(f"✅ {self.name}: Market regime favorable for trading")
            return True, "Market regime OK"

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during filter check: {e}")
            return False, f"Filter error: {e}"

    def _check_atr_volatility(self, market_state: Dict) -> Tuple[bool, str]:
        """
        ATR must be in stable range (not too low, not too extreme)
        """
        # Use primary timeframe (15m) for ATR check
        timeframes = market_state.get('timeframes', {})

        # Try to get 15m, fall back to first available
        tf_data = None
        for tf in ['15m', '5m', '1H', '4H']:
            if tf in timeframes:
                tf_data = timeframes[tf]
                break

        if not tf_data or not tf_data.get('atr'):
            return False, "No ATR data available"

        atr_data = tf_data['atr']
        atr_percentile = atr_data.get('atr_percentile', 50)

        # ATR should be above minimum (avoid dead markets)
        if atr_percentile < ATR_MIN_PERCENTILE:
            return False, f"ATR too low ({atr_percentile:.1f}th percentile < {ATR_MIN_PERCENTILE})"

        # ATR should be below maximum (avoid extreme volatility)
        if atr_percentile > ATR_MAX_PERCENTILE:
            return False, f"ATR too high ({atr_percentile:.1f}th percentile > {ATR_MAX_PERCENTILE})"

        return True, f"ATR volatility OK ({atr_percentile:.1f}th percentile)"

    def _check_funding_rate(self, market_state: Dict) -> Tuple[bool, str]:
        """
        Funding rate must not be extreme (indicates crowded trade)
        """
        funding = market_state.get('funding_rate')

        if not funding:
            # No funding data might mean spot market - allow
            logger.warning(f"{self.name}: No funding rate data (spot market?)")
            return True, "No funding rate data (assumed OK)"

        funding_rate = funding.get('funding_rate', 0)

        # Check if funding is extreme
        if funding_rate > FUNDING_RATE_MAX:
            return False, f"Funding rate too high ({funding_rate:.4f} > {FUNDING_RATE_MAX})"

        if funding_rate < FUNDING_RATE_MIN:
            return False, f"Funding rate too negative ({funding_rate:.4f} < {FUNDING_RATE_MIN})"

        return True, f"Funding rate OK ({funding_rate:.4f})"

    def _check_open_interest(self, market_state: Dict) -> Tuple[bool, str]:
        """
        Open Interest should be relatively stable
        Large changes indicate instability
        """
        oi = market_state.get('open_interest')

        if not oi:
            # No OI data might mean spot market - allow
            logger.warning(f"{self.name}: No open interest data (spot market?)")
            return True, "No OI data (assumed OK)"

        current_oi = oi.get('open_interest', 0)

        # If we have previous OI, check for extreme changes
        if self.last_oi is not None and self.last_oi > 0:
            oi_change = abs(current_oi - self.last_oi) / self.last_oi

            if oi_change > OI_CHANGE_MAX:
                return False, f"OI changed too much ({oi_change*100:.1f}% > {OI_CHANGE_MAX*100:.1f}%)"

        # Update last OI
        self.last_oi = current_oi

        return True, f"Open Interest stable"

    def _check_compression_for_breakout(self, market_state: Dict) -> Tuple[bool, str]:
        """
        Check for volatility compression (ideal for breakout strategy)
        This is a bonus condition, not strictly required
        """
        timeframes = market_state.get('timeframes', {})

        # Check compression on multiple timeframes
        compressed_count = 0
        for tf in ['15m', '1H', '4H']:
            if tf in timeframes:
                tf_data = timeframes[tf]
                if tf_data.get('atr', {}).get('is_compressed', False):
                    compressed_count += 1

        if compressed_count >= 2:
            return True, f"Volatility compression detected on {compressed_count} timeframes"

        return False, "No compression detected"

    def get_regime_score(self, market_state: Dict) -> float:
        """
        Calculate overall market regime quality score (0-1)
        Higher = better conditions
        """
        score = 0.0
        max_score = 4.0

        # ATR in good range (+1)
        atr_check = self._check_atr_volatility(market_state)
        if atr_check[0]:
            score += 1.0

        # Funding rate OK (+1)
        funding_check = self._check_funding_rate(market_state)
        if funding_check[0]:
            score += 1.0

        # OI stable (+1)
        oi_check = self._check_open_interest(market_state)
        if oi_check[0]:
            score += 1.0

        # Compression present (+1 bonus)
        compression_check = self._check_compression_for_breakout(market_state)
        if compression_check[0]:
            score += 1.0

        return score / max_score

    def reset(self):
        """Reset filter state"""
        self.last_oi = None
