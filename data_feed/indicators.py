"""
Technical Indicators
Calculates ATR, volatility metrics, and other technical indicators
All calculations are vectorized for performance
"""

import numpy as np
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """
    Collection of technical indicator calculations
    """

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float],
                     period: int = 14) -> Optional[float]:
        """
        Calculate Average True Range (ATR)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            period: ATR period (default 14)

        Returns:
            Current ATR value
        """
        if len(highs) < period + 1:
            return None

        highs = np.array(highs)
        lows = np.array(lows)
        closes = np.array(closes)

        # Calculate True Range
        high_low = highs - lows
        high_close = np.abs(highs - np.roll(closes, 1))
        low_close = np.abs(lows - np.roll(closes, 1))

        true_range = np.maximum(high_low, high_close)
        true_range = np.maximum(true_range, low_close)

        # Skip first value (no previous close)
        true_range = true_range[1:]

        # Calculate ATR using exponential moving average
        atr = np.mean(true_range[-period:])

        return float(atr)

    @staticmethod
    def calculate_atr_series(highs: List[float], lows: List[float], closes: List[float],
                            period: int = 14) -> List[float]:
        """
        Calculate ATR series for entire dataset
        """
        if len(highs) < period + 1:
            return []

        highs = np.array(highs)
        lows = np.array(lows)
        closes = np.array(closes)

        # Calculate True Range
        high_low = highs - lows
        high_close = np.abs(highs - np.roll(closes, 1))
        low_close = np.abs(lows - np.roll(closes, 1))

        true_range = np.maximum(high_low, high_close)
        true_range = np.maximum(true_range, low_close)
        true_range[0] = high_low[0]  # First value

        # Calculate ATR using EMA
        atr_values = []
        atr = np.mean(true_range[:period])
        atr_values.append(atr)

        alpha = 1 / period
        for i in range(period, len(true_range)):
            atr = alpha * true_range[i] + (1 - alpha) * atr
            atr_values.append(atr)

        return atr_values

    @staticmethod
    def calculate_atr_percentile(current_atr: float, atr_series: List[float]) -> float:
        """
        Calculate percentile rank of current ATR in historical distribution

        Returns:
            Percentile (0-100)
        """
        if not atr_series:
            return 50.0

        atr_array = np.array(atr_series)
        percentile = (np.sum(atr_array < current_atr) / len(atr_array)) * 100
        return float(percentile)

    @staticmethod
    def is_volatility_compressed(atr_series: List[float], threshold: float = 0.7) -> bool:
        """
        Check if volatility is compressed (ATR near recent lows)

        Args:
            atr_series: Series of ATR values
            threshold: Compression threshold (0-1), lower = more compressed

        Returns:
            True if volatility is compressed
        """
        if len(atr_series) < 20:
            return False

        current_atr = atr_series[-1]
        recent_max = np.max(atr_series[-20:])

        compression_ratio = current_atr / recent_max if recent_max > 0 else 1.0

        return compression_ratio < threshold

    @staticmethod
    def calculate_bollinger_bands(closes: List[float], period: int = 20,
                                 std_dev: float = 2.0) -> Tuple[List[float], List[float], List[float]]:
        """
        Calculate Bollinger Bands

        Returns:
            (upper_band, middle_band, lower_band)
        """
        if len(closes) < period:
            return [], [], []

        closes_array = np.array(closes)

        # Calculate moving average and standard deviation
        sma = np.convolve(closes_array, np.ones(period)/period, mode='valid')

        std = []
        for i in range(len(sma)):
            window = closes_array[i:i+period]
            std.append(np.std(window))
        std = np.array(std)

        upper_band = sma + (std_dev * std)
        lower_band = sma - (std_dev * std)

        return upper_band.tolist(), sma.tolist(), lower_band.tolist()

    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
        """
        Calculate Relative Strength Index (RSI)
        """
        if len(closes) < period + 1:
            return None

        closes_array = np.array(closes)
        deltas = np.diff(closes_array)

        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi)

    @staticmethod
    def calculate_ema(values: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average
        """
        if len(values) < period:
            return []

        values_array = np.array(values)
        ema_values = []

        # Initial SMA
        sma = np.mean(values_array[:period])
        ema_values.append(sma)

        # Calculate EMA
        multiplier = 2 / (period + 1)
        for i in range(period, len(values)):
            ema = (values_array[i] - ema_values[-1]) * multiplier + ema_values[-1]
            ema_values.append(ema)

        return ema_values

    @staticmethod
    def calculate_volume_delta(volumes: List[float], closes: List[float]) -> List[float]:
        """
        Calculate volume delta (buying vs selling pressure)
        Positive delta = buying pressure, Negative = selling pressure
        """
        if len(volumes) < 2 or len(closes) < 2:
            return []

        volumes_array = np.array(volumes)
        closes_array = np.array(closes)

        # Calculate price direction
        price_changes = np.diff(closes_array)

        # Approximate buy/sell volume based on price direction
        volume_delta = []
        for i in range(len(price_changes)):
            if price_changes[i] > 0:
                # Price up = buying pressure
                delta = volumes_array[i+1]
            elif price_changes[i] < 0:
                # Price down = selling pressure
                delta = -volumes_array[i+1]
            else:
                # No change
                delta = 0
            volume_delta.append(delta)

        return volume_delta

    @staticmethod
    def calculate_support_resistance(highs: List[float], lows: List[float],
                                    closes: List[float], lookback: int = 50) -> Tuple[List[float], List[float]]:
        """
        Calculate support and resistance levels using swing points

        Returns:
            (support_levels, resistance_levels)
        """
        if len(highs) < lookback or len(lows) < lookback:
            return [], []

        highs_array = np.array(highs[-lookback:])
        lows_array = np.array(lows[-lookback:])

        # Find swing highs (resistance)
        resistance = []
        for i in range(2, len(highs_array) - 2):
            if (highs_array[i] > highs_array[i-1] and highs_array[i] > highs_array[i-2] and
                highs_array[i] > highs_array[i+1] and highs_array[i] > highs_array[i+2]):
                resistance.append(float(highs_array[i]))

        # Find swing lows (support)
        support = []
        for i in range(2, len(lows_array) - 2):
            if (lows_array[i] < lows_array[i-1] and lows_array[i] < lows_array[i-2] and
                lows_array[i] < lows_array[i+1] and lows_array[i] < lows_array[i+2]):
                support.append(float(lows_array[i]))

        return support, resistance

    @staticmethod
    def calculate_trend_strength(closes: List[float], period: int = 20) -> float:
        """
        Calculate trend strength (0-1)
        Uses linear regression slope and R-squared

        Returns:
            Trend strength: 0 = no trend, 1 = strong trend
        """
        if len(closes) < period:
            return 0.0

        closes_array = np.array(closes[-period:])
        x = np.arange(len(closes_array))

        # Linear regression
        coeffs = np.polyfit(x, closes_array, 1)
        slope = coeffs[0]

        # Calculate R-squared
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((closes_array - y_pred) ** 2)
        ss_tot = np.sum((closes_array - np.mean(closes_array)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        # Normalize slope
        price_range = np.max(closes_array) - np.min(closes_array)
        normalized_slope = abs(slope) / (price_range / period) if price_range != 0 else 0

        # Combine R-squared and normalized slope
        trend_strength = (r_squared + min(normalized_slope, 1.0)) / 2

        return float(np.clip(trend_strength, 0, 1))

    @staticmethod
    def detect_divergence(prices: List[float], indicator: List[float],
                         lookback: int = 10) -> Optional[str]:
        """
        Detect bullish or bearish divergence

        Returns:
            'bullish', 'bearish', or None
        """
        if len(prices) < lookback or len(indicator) < lookback:
            return None

        prices_array = np.array(prices[-lookback:])
        indicator_array = np.array(indicator[-lookback:])

        # Price trend
        price_coeffs = np.polyfit(np.arange(lookback), prices_array, 1)
        price_slope = price_coeffs[0]

        # Indicator trend
        ind_coeffs = np.polyfit(np.arange(lookback), indicator_array, 1)
        ind_slope = ind_coeffs[0]

        # Detect divergence
        if price_slope < -0.001 and ind_slope > 0.001:
            return 'bullish'  # Price down, indicator up
        elif price_slope > 0.001 and ind_slope < -0.001:
            return 'bearish'  # Price up, indicator down

        return None
