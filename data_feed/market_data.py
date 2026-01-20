"""
Market Data Feed
Aggregates all market data from OKX and provides unified interface
Handles caching, multi-timeframe data, and derived metrics
"""

import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from .okx_client import OKXClient
from .indicators import TechnicalIndicators
from config import ENABLE_CACHE, CACHE_EXPIRY_SECONDS

logger = logging.getLogger(__name__)


class MarketDataFeed:
    """
    Main market data aggregator
    Provides clean interface for all trading data needs
    """

    def __init__(self, okx_client: Optional[OKXClient] = None):
        self.client = okx_client or OKXClient()
        self.indicators = TechnicalIndicators()

        # Data cache
        self.cache = {} if ENABLE_CACHE else None
        self.cache_timestamps = {}

    def _get_cache_key(self, *args) -> str:
        """Generate cache key from arguments"""
        return '_'.join(str(arg) for arg in args)

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid"""
        if not ENABLE_CACHE or key not in self.cache_timestamps:
            return False

        age = time.time() - self.cache_timestamps[key]
        return age < CACHE_EXPIRY_SECONDS

    def _cache_data(self, key: str, data: any):
        """Store data in cache"""
        if ENABLE_CACHE:
            self.cache[key] = data
            self.cache_timestamps[key] = time.time()

    def _get_cached_data(self, key: str) -> Optional[any]:
        """Retrieve cached data if valid"""
        if self._is_cache_valid(key):
            return self.cache.get(key)
        return None

    # =====================================
    # MULTI-TIMEFRAME CANDLE DATA
    # =====================================

    def get_multi_timeframe_data(self, symbol: str, timeframes: List[str],
                                 limit: int = 100) -> Dict[str, List[Dict]]:
        """
        Get candle data for multiple timeframes at once

        Args:
            symbol: Trading pair (e.g., 'BTC-USDT')
            timeframes: List of timeframes ['1m', '5m', '15m', '1h', '4h']
            limit: Number of candles per timeframe

        Returns:
            Dict mapping timeframe to candle data
        """
        result = {}

        for tf in timeframes:
            cache_key = self._get_cache_key('candles', symbol, tf, limit)
            cached = self._get_cached_data(cache_key)

            if cached is not None:
                result[tf] = cached
                continue

            raw_candles = self.client.get_candles(symbol, tf, limit)
            if raw_candles:
                # Convert to structured format
                candles = self._format_candles(raw_candles)
                result[tf] = candles
                self._cache_data(cache_key, candles)
            else:
                logger.warning(f"Failed to fetch {tf} candles for {symbol}")
                result[tf] = []

        return result

    def _format_candles(self, raw_candles: List[List]) -> List[Dict]:
        """
        Convert OKX raw candle format to structured dict

        OKX format: [timestamp, open, high, low, close, volume, volumeCcy]
        """
        candles = []
        for candle in raw_candles:
            candles.append({
                'timestamp': int(candle[0]),
                'datetime': datetime.fromtimestamp(int(candle[0]) / 1000),
                'open': float(candle[1]),
                'high': float(candle[2]),
                'low': float(candle[3]),
                'close': float(candle[4]),
                'volume': float(candle[5]),
                'volume_ccy': float(candle[6]) if len(candle) > 6 else 0
            })
        # OKX returns newest first, reverse to oldest first
        return list(reversed(candles))

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price"""
        cache_key = self._get_cache_key('ticker', symbol)
        cached = self._get_cached_data(cache_key)

        if cached is not None:
            return cached

        ticker = self.client.get_ticker(symbol)
        if ticker and 'last' in ticker:
            price = float(ticker['last'])
            self._cache_data(cache_key, price)
            return price

        return None

    # =====================================
    # MARKET METRICS
    # =====================================

    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Get current funding rate

        Returns:
            {
                'funding_rate': float,
                'funding_time': datetime,
                'next_funding_time': datetime
            }
        """
        cache_key = self._get_cache_key('funding', symbol)
        cached = self._get_cached_data(cache_key)

        if cached is not None:
            return cached

        funding = self.client.get_funding_rate(symbol)
        if funding:
            result = {
                'funding_rate': float(funding.get('fundingRate', 0)),
                'funding_time': datetime.fromtimestamp(int(funding.get('fundingTime', 0)) / 1000),
                'next_funding_time': datetime.fromtimestamp(int(funding.get('nextFundingTime', 0)) / 1000)
            }
            self._cache_data(cache_key, result)
            return result

        return None

    def get_open_interest(self, symbol: str) -> Optional[Dict]:
        """
        Get open interest data

        Returns:
            {
                'open_interest': float,
                'open_interest_ccy': float,
                'timestamp': datetime
            }
        """
        cache_key = self._get_cache_key('oi', symbol)
        cached = self._get_cached_data(cache_key)

        if cached is not None:
            return cached

        oi_data = self.client.get_open_interest(symbol)
        if oi_data:
            result = {
                'open_interest': float(oi_data.get('oi', 0)),
                'open_interest_ccy': float(oi_data.get('oiCcy', 0)),
                'timestamp': datetime.fromtimestamp(int(oi_data.get('ts', 0)) / 1000)
            }
            self._cache_data(cache_key, result)
            return result

        return None

    def get_liquidation_heatmap(self, symbol: str, limit: int = 100) -> Optional[List[Dict]]:
        """
        Get recent liquidations for heatmap analysis

        Returns:
            List of liquidation events with price levels
        """
        cache_key = self._get_cache_key('liquidations', symbol, limit)
        cached = self._get_cached_data(cache_key)

        if cached is not None:
            return cached

        liquidations = self.client.get_liquidation_orders(symbol, limit=limit)
        if liquidations:
            formatted = []
            for liq in liquidations:
                formatted.append({
                    'side': liq.get('side'),
                    'price': float(liq.get('bkPx', 0)),
                    'size': float(liq.get('sz', 0)),
                    'timestamp': datetime.fromtimestamp(int(liq.get('ts', 0)) / 1000)
                })
            self._cache_data(cache_key, formatted)
            return formatted

        return None

    def get_orderbook_depth(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """
        Get orderbook for liquidity analysis

        Returns:
            {
                'bids': [(price, size), ...],
                'asks': [(price, size), ...],
                'spread': float,
                'mid_price': float
            }
        """
        orderbook = self.client.get_orderbook(symbol, depth)
        if not orderbook:
            return None

        bids = [(float(b[0]), float(b[1])) for b in orderbook.get('bids', [])]
        asks = [(float(a[0]), float(a[1])) for a in orderbook.get('asks', [])]

        if not bids or not asks:
            return None

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = best_ask - best_bid
        mid_price = (best_bid + best_ask) / 2

        return {
            'bids': bids,
            'asks': asks,
            'spread': spread,
            'mid_price': mid_price,
            'timestamp': datetime.fromtimestamp(int(orderbook.get('ts', 0)) / 1000)
        }

    # =====================================
    # TECHNICAL INDICATORS
    # =====================================

    def calculate_atr_for_timeframe(self, symbol: str, timeframe: str,
                                   period: int = 14, limit: int = 100) -> Optional[Dict]:
        """
        Calculate ATR and related volatility metrics

        Returns:
            {
                'atr': float,
                'atr_series': List[float],
                'atr_percentile': float,
                'is_compressed': bool
            }
        """
        candles = self.get_multi_timeframe_data(symbol, [timeframe], limit)[timeframe]
        if not candles or len(candles) < period + 1:
            return None

        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        closes = [c['close'] for c in candles]

        # Calculate ATR
        atr = self.indicators.calculate_atr(highs, lows, closes, period)
        atr_series = self.indicators.calculate_atr_series(highs, lows, closes, period)

        if not atr or not atr_series:
            return None

        # Additional metrics
        atr_percentile = self.indicators.calculate_atr_percentile(atr, atr_series)
        is_compressed = self.indicators.is_volatility_compressed(atr_series)

        return {
            'atr': atr,
            'atr_series': atr_series,
            'atr_percentile': atr_percentile,
            'is_compressed': is_compressed,
            'current_price': closes[-1]
        }

    def calculate_trend_metrics(self, symbol: str, timeframe: str,
                               period: int = 20, limit: int = 100) -> Optional[Dict]:
        """
        Calculate trend strength and direction

        Returns:
            {
                'trend_strength': float (0-1),
                'trend_direction': str ('up', 'down', 'sideways'),
                'rsi': float,
                'ema_short': float,
                'ema_long': float
            }
        """
        candles = self.get_multi_timeframe_data(symbol, [timeframe], limit)[timeframe]
        if not candles or len(candles) < period + 1:
            return None

        closes = [c['close'] for c in candles]

        # Trend strength
        trend_strength = self.indicators.calculate_trend_strength(closes, period)

        # Determine direction
        ema_short = self.indicators.calculate_ema(closes, period // 2)
        ema_long = self.indicators.calculate_ema(closes, period)

        if ema_short and ema_long:
            if ema_short[-1] > ema_long[-1] * 1.001:  # 0.1% threshold
                trend_direction = 'up'
            elif ema_short[-1] < ema_long[-1] * 0.999:
                trend_direction = 'down'
            else:
                trend_direction = 'sideways'
        else:
            trend_direction = 'sideways'

        # RSI
        rsi = self.indicators.calculate_rsi(closes, 14)

        return {
            'trend_strength': trend_strength,
            'trend_direction': trend_direction,
            'rsi': rsi or 50.0,
            'ema_short': ema_short[-1] if ema_short else closes[-1],
            'ema_long': ema_long[-1] if ema_long else closes[-1],
            'current_price': closes[-1]
        }

    def get_volume_analysis(self, symbol: str, timeframe: str, limit: int = 50) -> Optional[Dict]:
        """
        Analyze volume patterns

        Returns:
            {
                'current_volume': float,
                'avg_volume': float,
                'volume_ratio': float,
                'volume_trend': str,
                'volume_delta_positive': bool
            }
        """
        candles = self.get_multi_timeframe_data(symbol, [timeframe], limit)[timeframe]
        if not candles or len(candles) < 10:
            return None

        volumes = [c['volume'] for c in candles]
        closes = [c['close'] for c in candles]

        current_volume = volumes[-1]
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        # Volume trend
        recent_avg = sum(volumes[-5:]) / 5
        older_avg = sum(volumes[-10:-5]) / 5
        volume_trend = 'increasing' if recent_avg > older_avg * 1.1 else \
                      'decreasing' if recent_avg < older_avg * 0.9 else 'stable'

        # Volume delta
        volume_deltas = self.indicators.calculate_volume_delta(volumes, closes)
        volume_delta_positive = sum(volume_deltas[-5:]) > 0 if volume_deltas else False

        return {
            'current_volume': current_volume,
            'avg_volume': avg_volume,
            'volume_ratio': volume_ratio,
            'volume_trend': volume_trend,
            'volume_delta_positive': volume_delta_positive
        }

    # =====================================
    # COMPREHENSIVE MARKET STATE
    # =====================================

    def get_market_state(self, symbol: str, timeframes: List[str]) -> Dict:
        """
        Get comprehensive market state across all timeframes
        This is the main method filters will use

        Returns complete market snapshot with all necessary data
        """
        logger.info(f"Fetching market state for {symbol}")

        # Get multi-timeframe candles
        candle_data = self.get_multi_timeframe_data(symbol, timeframes, limit=200)

        # Get market metrics
        # Funding rate and open interest only exist for perpetuals (SWAP)
        is_perpetual = 'SWAP' in symbol.upper()
        funding = self.get_funding_rate(symbol) if is_perpetual else None
        oi = self.get_open_interest(symbol) if is_perpetual else None
        current_price = self.get_current_price(symbol)

        # Calculate indicators for each timeframe
        indicators_by_tf = {}
        for tf in timeframes:
            if candle_data[tf]:
                atr_data = self.calculate_atr_for_timeframe(symbol, tf)
                trend_data = self.calculate_trend_metrics(symbol, tf)
                volume_data = self.get_volume_analysis(symbol, tf)

                indicators_by_tf[tf] = {
                    'atr': atr_data,
                    'trend': trend_data,
                    'volume': volume_data,
                    'candles': candle_data[tf]
                }

        market_state = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'current_price': current_price,
            'funding_rate': funding,
            'open_interest': oi,
            'timeframes': indicators_by_tf
        }

        return market_state

    # =====================================
    # UTILITY METHODS
    # =====================================

    def clear_cache(self):
        """Clear all cached data"""
        if ENABLE_CACHE:
            self.cache.clear()
            self.cache_timestamps.clear()
            logger.info("Cache cleared")

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        if not ENABLE_CACHE:
            return {'enabled': False}

        return {
            'enabled': True,
            'items': len(self.cache),
            'size_bytes': sum(len(str(v)) for v in self.cache.values())
        }
