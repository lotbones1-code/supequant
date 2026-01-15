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
                try:
                    logger.info(f"   ✅ {tf}: Loading from cache")
                    with open(cache_file, 'r') as f:
                        cached_data = json.load(f)
                    
                    # Validate cache data quality
                    if isinstance(cached_data, list) and len(cached_data) > 0:
                        # Check if data looks reasonable (has expected structure)
                        first_candle = cached_data[0]
                        if isinstance(first_candle, dict) and 'timestamp' in first_candle:
                            # Deduplicate cached data (in case cache has duplicates)
                            seen_timestamps = set()
                            unique_cached = []
                            for candle in cached_data:
                                if candle.get('timestamp') not in seen_timestamps:
                                    seen_timestamps.add(candle['timestamp'])
                                    unique_cached.append(candle)
                            
                            if len(unique_cached) < len(cached_data):
                                logger.warning(f"   ⚠️  {tf}: Removed {len(cached_data) - len(unique_cached)} duplicates from cache")
                            
                            data[tf] = unique_cached
                            logger.info(f"      Loaded {len(unique_cached)} unique candles from cache")
                        else:
                            logger.warning(f"   ⚠️  {tf}: Cache file has invalid structure, fetching fresh data")
                            force_refresh = True
                    else:
                        logger.warning(f"   ⚠️  {tf}: Cache file is empty, fetching fresh data")
                        force_refresh = True
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"   ⚠️  {tf}: Cache file corrupted ({e}), fetching fresh data")
                    force_refresh = True
            
            if force_refresh or tf not in data:
                # Fetch from API
                logger.info(f"   📡 {tf}: Fetching from OKX API...")
                candles = self._fetch_candles(symbol, tf, start_date, end_date)

                if candles:
                    data[tf] = candles
                    # Cache the data
                    self._save_to_cache(cache_file, candles)
                    logger.info(f"   ✅ {tf}: Fetched {len(candles)} candles")
                else:
                    # For 4H and 1H timeframes, if no data (common for recent data),
                    # fall back to using 15m data aggregated or skip gracefully
                    if tf in ['4H', '1H']:
                        logger.warning(f"   ⚠️  {tf}: No data available (may be too recent for completed candles)")
                        logger.warning(f"      Falling back to 15m data for this timeframe")
                        # Use 15m data as fallback - the filters will handle missing HTF data
                        if '15m' in data and data['15m']:
                            data[tf] = data['15m']  # Use 15m candles as fallback
                            logger.info(f"      Using {len(data[tf])} candles from 15m as fallback")
                        else:
                            data[tf] = []
                    else:
                        logger.error(f"   ❌ {tf}: Failed to fetch data")
                        data[tf] = []

        # Log detailed information about loaded data
        logger.info(f"\n📊 Data Loading Summary for {symbol}:")
        logger.info(f"   Requested Period: {start_date} to {end_date}")
        for tf, candles in data.items():
            if candles:
                first_ts = datetime.fromtimestamp(candles[0]['timestamp'] / 1000)
                last_ts = datetime.fromtimestamp(candles[-1]['timestamp'] / 1000)
                logger.info(f"   {tf}: {len(candles)} candles")
                logger.info(f"      Date Range: {first_ts.strftime('%Y-%m-%d %H:%M')} to {last_ts.strftime('%Y-%m-%d %H:%M')}")
            else:
                logger.warning(f"   {tf}: NO DATA")
        
        # Validate data quality
        self._validate_data(data, start_date, end_date)

        return data

    def _fetch_candles_paginated(self, symbol: str, timeframe: str,
                                 start_ts: int, end_ts: int) -> List[Dict]:
        """
        Fetch candles with pagination to get more than 300 candles
        
        OKX regular endpoint caps at 300 candles. This method paginates
        using 'after' parameter to fetch all candles in the date range.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '15m', '1H')
            start_ts: Start timestamp in milliseconds
            end_ts: End timestamp in milliseconds
            
        Returns:
            List of candle dicts sorted by timestamp
        """
        all_candles = []
        current_end = end_ts  # Start from end timestamp
        max_calls = 50  # Safety limit
        call_count = 0
        
        # Calculate expected candles to estimate calls needed
        timeframe_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '1H': 60, '4H': 240
        }
        minutes_per_candle = timeframe_minutes.get(timeframe, 15)
        days = (end_ts - start_ts) / (1000 * 60 * 60 * 24)
        expected_candles = (days * 24 * 60) / minutes_per_candle
        estimated_calls = max(1, int(expected_candles / 300) + 1)
        
        logger.info(f"   📊 Estimated: {expected_candles:.0f} candles needed, ~{estimated_calls} API calls")
        
        while call_count < max_calls:
            call_count += 1
            
            try:
                # Fetch candles using 'after' parameter to paginate backwards
                # OKX returns candles after the specified timestamp (newer candles)
                # We'll work backwards by updating current_end to oldest timestamp
                candles_raw = self.client.get_history_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    after=str(current_end),
                    limit=300  # Max for regular endpoint
                )
                
                if not candles_raw or len(candles_raw) == 0:
                    logger.debug(f"   No more candles returned (call {call_count})")
                    break
                
                # Convert OKX format to our format
                batch_candles = []
                for candle in candles_raw:
                    ts = int(candle[0])
                    batch_candles.append({
                        'timestamp': ts,
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': float(candle[5])
                    })
                
                # OKX returns newest first, so sort to get chronological order
                batch_candles.sort(key=lambda x: x['timestamp'])
                
                # Find oldest and newest timestamps in this batch
                if batch_candles:
                    oldest_ts = batch_candles[0]['timestamp']
                    newest_ts = batch_candles[-1]['timestamp']
                    
                    logger.info(f"   📥 Call {call_count}: Fetched {len(batch_candles)} candles "
                              f"({datetime.fromtimestamp(oldest_ts/1000).strftime('%Y-%m-%d %H:%M')} to "
                              f"{datetime.fromtimestamp(newest_ts/1000).strftime('%Y-%m-%d %H:%M')})")
                    
                    all_candles.extend(batch_candles)
                    
                    # If oldest candle is before or equal to start_ts, we've got all we need
                    if oldest_ts <= start_ts:
                        logger.info(f"   ✅ Reached start date, stopping pagination")
                        break
                    
                    # Move 'after' cursor to oldest timestamp for next iteration
                    # This gets us older candles in the next call (going backwards)
                    current_end = oldest_ts
                else:
                    break
                
                # Rate limiting
                time.sleep(0.15)
                
            except Exception as e:
                logger.error(f"   Error in paginated fetch (call {call_count}): {e}")
                import traceback
                logger.error(traceback.format_exc())
                break
        
        # Filter to requested date range
        filtered_candles = [c for c in all_candles if start_ts <= c['timestamp'] <= end_ts]
        
        # Sort by timestamp (oldest first)
        filtered_candles.sort(key=lambda x: x['timestamp'])
        
        # Deduplicate by timestamp
        seen = set()
        unique_candles = []
        for c in filtered_candles:
            if c['timestamp'] not in seen:
                seen.add(c['timestamp'])
                unique_candles.append(c)
        
        if len(unique_candles) < len(filtered_candles):
            logger.info(f"   Removed {len(filtered_candles) - len(unique_candles)} duplicate candles")
        
        logger.info(f"   ✅ Paginated fetch complete: {len(unique_candles)} unique candles "
                   f"(from {len(all_candles)} total fetched)")
        
        return unique_candles

    def _fetch_candles(self, symbol: str, timeframe: str,
                      start_date: str, end_date: str) -> List[Dict]:
        """
        Fetch candles from OKX API
        
        IMPORTANT: OKX has two endpoints:
        - /api/v5/market/candles: Returns RECENT data only (last ~24 hours), can't request specific dates
        - /api/v5/market/history-candles: Returns historical data for specific dates
        
        For recent data (regular candles endpoint), we accept whatever the API returns
        without date filtering. For historical data, we filter by date range.
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        all_candles = []
        
        # Convert to milliseconds
        end_ts = int(end_dt.timestamp() * 1000)
        start_ts = int(start_dt.timestamp() * 1000)
        now_ts = int(time.time() * 1000)
        three_months_ago_ms = now_ts - (90 * 24 * 60 * 60 * 1000)
        
        # Determine if we're requesting recent data (will use regular candles endpoint)
        # Regular candles endpoint only returns recent data, can't filter by date
        is_recent_data = end_ts > three_months_ago_ms
        
        if is_recent_data:
            logger.info(f"   Fetching {timeframe} data (recent data - will use regular candles endpoint)")
            logger.info(f"   NOTE: Regular candles endpoint returns recent data only, not specific date ranges")
            logger.info(f"   Requesting WITHOUT 'before' parameter to get maximum candles (up to 300)")
        else:
            logger.info(f"   Fetching {timeframe} data from {start_date} to {end_date} (historical data)")
        
        max_retries = 50  # Prevent infinite loops
        retry_count = 0
        
        # For recent data, use paginated fetch to get more than 300 candles
        # For historical data, use pagination with 'before'
        if is_recent_data:
            # Use paginated fetch for recent data to get all candles in date range
            logger.info(f"   Using paginated fetch for recent data (regular endpoint, max 300 per call)")
            try:
                unique_candles = self._fetch_candles_paginated(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_ts=start_ts,
                    end_ts=end_ts
                )
                all_candles.extend(unique_candles)
            except Exception as e:
                logger.error(f"   Error in paginated fetch: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            # For historical data: use pagination with 'before' parameter
            current_before = end_ts
            
            while retry_count < max_retries:
                retry_count += 1
                
                try:
                    # Use 'before' to get candles before (older than) current_before
                    logger.debug(f"   Requesting candles before timestamp: {current_before} ({datetime.fromtimestamp(current_before/1000)})")
                    
                    candles = self.client.get_history_candles(
                        symbol=symbol,
                        timeframe=timeframe,
                        before=str(current_before),
                        limit=100
                    )
                    
                    if not candles or len(candles) == 0:
                        logger.debug(f"   No more candles returned")
                        break
                    
                    # Convert OKX format to our format
                    # ACCEPT ALL CANDLES - no validation based on recency or date range
                    # The API returns what it returns, and we use it for backtesting
                    batch_candles = []
                    for candle in candles:
                        # OKX format: [timestamp, open, high, low, close, volume, ...]
                        ts = int(candle[0])
                        
                        # Accept all candles regardless of timestamp - no filtering by recency or date range
                        batch_candles.append({
                            'timestamp': ts,
                            'open': float(candle[1]),
                            'high': float(candle[2]),
                            'low': float(candle[3]),
                            'close': float(candle[4]),
                            'volume': float(candle[5])
                        })
                    
                    all_candles.extend(batch_candles)
                    
                    logger.info(f"   Accepted {len(batch_candles)} candles from API (no recency validation)")
                    
                    # Continue pagination if we got candles
                    if batch_candles:
                        oldest_ts = min(c['timestamp'] for c in batch_candles)
                        
                        # Move before cursor to oldest timestamp for next iteration
                        current_before = oldest_ts
                    else:
                        # No more candles, stop
                        break
                    
                    # Rate limiting
                    time.sleep(0.15)
                    
                    if retry_count % 10 == 0:
                        logger.info(f"   Fetched {len(all_candles)} candles so far...")
                        
                except Exception as e:
                    logger.error(f"   Error fetching: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    break
        
        # Sort by timestamp (oldest first)
        all_candles.sort(key=lambda x: x['timestamp'])
        
        # Deduplicate by timestamp
        seen = set()
        unique_candles = []
        for c in all_candles:
            if c['timestamp'] not in seen:
                seen.add(c['timestamp'])
                unique_candles.append(c)
        
        logger.info(f"   Total: {len(unique_candles)} unique candles for {timeframe}")
        if unique_candles:
            first_ts = datetime.fromtimestamp(unique_candles[0]['timestamp'] / 1000)
            last_ts = datetime.fromtimestamp(unique_candles[-1]['timestamp'] / 1000)
            logger.info(f"   Actual data range: {first_ts} to {last_ts}")
            logger.info(f"   ✅ Accepted all candles from API (no recency validation applied)")
        
        return unique_candles

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
