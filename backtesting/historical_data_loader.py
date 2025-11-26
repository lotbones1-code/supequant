"""
Historical Data Loader for Backtesting
Fetches and caches historical OHLCV data from OKX API

This module:
- Downloads historical candle data for SOL and BTC
- Caches data locally to avoid repeated API calls
- Handles multiple timeframes (1m, 5m, 15m, 1H, 4H)
- Validates data quality
- Provides data in format compatible with existing filters
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import time
from data_feed.okx_client import OKXClient
import config

logger = logging.getLogger(__name__)


class HistoricalDataLoader:
    """
    Loads historical market data for backtesting

    Features:
    - Multi-timeframe data fetching
    - Local caching to avoid API rate limits
    - Data validation and quality checks
    - Compatible with existing filter system
    """

    def __init__(self, cache_dir: str = "backtesting/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # OKXClient reads credentials from config.py directly
        self.client = OKXClient()

        self.timeframes = {
            '1m': '1m',
            '5m': '5m',
            '15m': '15m',
            '1H': '1H',
            '4H': '4H'
        }

        logger.info(f"📦 HistoricalDataLoader initialized (cache: {cache_dir})")

    def load_data(self, symbol: str, start_date: str, end_date: str,
                  timeframes: Optional[List[str]] = None,
                  force_refresh: bool = False) -> Dict:
        """
        Load historical data for a symbol across multiple timeframes

        Args:
            symbol: Trading symbol (e.g., 'SOL-USDT-SWAP')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            timeframes: List of timeframes to load (default: all)
            force_refresh: If True, ignore cache and fetch fresh data

        Returns:
            Dict with structure:
            {
                '1m': [candles],
                '5m': [candles],
                '15m': [candles],
                '1H': [candles],
                '4H': [candles]
            }
        """
        if timeframes is None:
            timeframes = list(self.timeframes.keys())

        logger.info(f"📥 Loading historical data for {symbol}")
        logger.info(f"   Period: {start_date} to {end_date}")
        logger.info(f"   Timeframes: {', '.join(timeframes)}")

        data = {}

        for tf in timeframes:
            cache_file = self._get_cache_filename(symbol, tf, start_date, end_date)

            # Try to load from cache first
            if not force_refresh and cache_file.exists():
                logger.info(f"   ✅ {tf}: Loading from cache")
                with open(cache_file, 'r') as f:
                    data[tf] = json.load(f)
            else:
                # Fetch from API
                logger.info(f"   📡 {tf}: Fetching from OKX API...")
                candles = self._fetch_candles(symbol, tf, start_date, end_date)

                if candles:
                    data[tf] = candles
                    # Cache the data
                    self._save_to_cache(cache_file, candles)
                    logger.info(f"   ✅ {tf}: Fetched {len(candles)} candles")
                else:
                    logger.error(f"   ❌ {tf}: Failed to fetch data")
                    data[tf] = []

        # Validate data quality
        self._validate_data(data, start_date, end_date)

        return data

    def _fetch_candles(self, symbol: str, timeframe: str,
                      start_date: str, end_date: str) -> List[Dict]:
        """
        Fetch candles from OKX API

        OKX API returns max 300 candles per request, so we need to paginate
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        all_candles = []
        current_end = end_dt

        # Calculate candle duration in minutes
        durations = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '1H': 60,
            '4H': 240
        }
        candle_minutes = durations.get(timeframe, 60)

        # OKX history-candles endpoint returns max 100 candles per request (vs 300 for live)
        max_candles_per_request = 100
        chunk_duration = timedelta(minutes=candle_minutes * max_candles_per_request)

        request_count = 0
        while current_end > start_dt:
            # Calculate chunk start (work backwards)
            chunk_start = max(start_dt, current_end - chunk_duration)

            # Convert to millisecond timestamps (OKX format)
            # Use 'before' parameter to get candles before (older than) current_end
            before_ts = int(current_end.timestamp() * 1000)

            # Progress logging every 10 requests
            request_count += 1
            if request_count % 10 == 0:
                logger.info(f"      Fetching chunk {request_count}... (current: {chunk_start.strftime('%Y-%m-%d')})")

            try:
                # Fetch historical candles using history-candles endpoint
                # Note: get_history_candles returns data list directly (not wrapped in dict)
                # Using 'before' parameter for historical data (get candles before this timestamp)
                logger.debug(f"Requesting: symbol={symbol}, tf={timeframe}, before={before_ts}, limit={max_candles_per_request}")
                logger.debug(f"Date range: {chunk_start} to {current_end}")

                candles = self.client.get_history_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    before=str(before_ts),
                    limit=max_candles_per_request
                )

                logger.debug(f"Response: {candles if candles is None else f'{len(candles)} candles'}")

                if candles:
                    logger.debug(f"Fetched {len(candles)} candles for {timeframe}")
                    # Convert OKX format to our format
                    for candle in candles:
                        # OKX format: [timestamp, open, high, low, close, volume, volumeCcy, volumeCcyQuote, confirm]
                        all_candles.append({
                            'timestamp': int(candle[0]),
                            'open': float(candle[1]),
                            'high': float(candle[2]),
                            'low': float(candle[3]),
                            'close': float(candle[4]),
                            'volume': float(candle[5])
                        })

                    # Move to next chunk
                    current_end = chunk_start

                    # Rate limiting
                    time.sleep(0.1)
                else:
                    logger.warning(f"⚠️  No data returned for {symbol} {timeframe} (before={before_ts})")
                    logger.warning(f"   Check: 1) Symbol format correct? 2) API credentials valid? 3) Date range valid?")
                    break

            except Exception as e:
                logger.error(f"❌ Error fetching candles for {symbol} {timeframe}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                break

        # Sort by timestamp (oldest first)
        all_candles.sort(key=lambda x: x['timestamp'])

        logger.info(f"   Downloaded {len(all_candles)} total candles for {symbol} {timeframe}")
        if all_candles:
            first_ts = datetime.fromtimestamp(all_candles[0]['timestamp'] / 1000)
            last_ts = datetime.fromtimestamp(all_candles[-1]['timestamp'] / 1000)
            logger.info(f"   Data range: {first_ts} to {last_ts}")

        # Filter to exact date range
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)
        logger.info(f"   Requested range: {start_dt} to {end_dt}")
        logger.info(f"   Requested timestamps: {start_ts} to {end_ts}")

        filtered_candles = [
            c for c in all_candles
            if start_ts <= c['timestamp'] <= end_ts
        ]

        logger.info(f"   After filtering: {len(filtered_candles)} candles")

        return filtered_candles

    def _get_cache_filename(self, symbol: str, timeframe: str,
                           start_date: str, end_date: str) -> Path:
        """Generate cache filename"""
        safe_symbol = symbol.replace('-', '_')
        filename = f"{safe_symbol}_{timeframe}_{start_date}_{end_date}.json"
        return self.cache_dir / filename

    def _save_to_cache(self, cache_file: Path, data: List[Dict]):
        """Save data to cache file"""
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"⚠️  Failed to save cache: {e}")

    def _validate_data(self, data: Dict, start_date: str, end_date: str):
        """
        Validate data quality

        Checks:
        - Data exists for all timeframes
        - No gaps in data
        - Reasonable number of candles
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end_dt - start_dt).days

        logger.info(f"\n📊 Data Quality Report:")
        logger.info(f"   Period: {days} days")

        for tf, candles in data.items():
            if not candles:
                logger.warning(f"   ⚠️  {tf}: NO DATA")
                continue

            # Calculate expected number of candles
            durations = {'1m': 1, '5m': 5, '15m': 15, '1H': 60, '4H': 240}
            candle_minutes = durations.get(tf, 60)
            expected_candles = (days * 24 * 60) / candle_minutes
            actual_candles = len(candles)
            completeness = (actual_candles / expected_candles) * 100

            # Check for gaps
            gaps = self._detect_gaps(candles, candle_minutes)

            status = "✅" if completeness > 95 and len(gaps) == 0 else "⚠️"
            logger.info(f"   {status} {tf}: {actual_candles} candles ({completeness:.1f}% complete, {len(gaps)} gaps)")

            if gaps and len(gaps) <= 5:
                for gap in gaps[:5]:
                    logger.warning(f"      Gap detected: {gap}")

    def _detect_gaps(self, candles: List[Dict], candle_minutes: int) -> List[str]:
        """Detect gaps in candle data"""
        gaps = []
        expected_gap_ms = candle_minutes * 60 * 1000

        for i in range(1, len(candles)):
            actual_gap = candles[i]['timestamp'] - candles[i-1]['timestamp']
            if actual_gap > expected_gap_ms * 1.5:  # Allow 50% tolerance
                gap_time = datetime.fromtimestamp(candles[i]['timestamp'] / 1000)
                gaps.append(f"{gap_time.strftime('%Y-%m-%d %H:%M')}")

        return gaps

    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear cached data

        Args:
            symbol: If provided, only clear cache for this symbol
        """
        if symbol:
            safe_symbol = symbol.replace('-', '_')
            pattern = f"{safe_symbol}_*.json"
            files = list(self.cache_dir.glob(pattern))
        else:
            files = list(self.cache_dir.glob("*.json"))

        for file in files:
            file.unlink()

        logger.info(f"🗑️  Cleared {len(files)} cache files")

    def get_cache_info(self) -> Dict:
        """Get information about cached data"""
        cache_files = list(self.cache_dir.glob("*.json"))

        info = {
            'total_files': len(cache_files),
            'total_size_mb': sum(f.stat().st_size for f in cache_files) / (1024 * 1024),
            'symbols': set()
        }

        for file in cache_files:
            parts = file.stem.split('_')
            if len(parts) >= 1:
                symbol = parts[0].replace('_', '-')
                info['symbols'].add(symbol)

        info['symbols'] = list(info['symbols'])

        return info
