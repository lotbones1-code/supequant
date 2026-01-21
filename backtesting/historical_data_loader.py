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
        Fetch candles from OKX API using history-candles endpoint
        
        IMPORTANT: For backtesting, we ALWAYS use the history-candles endpoint
        which accepts date range parameters via the 'before' parameter.
        
        The regular candles endpoint only returns the last 24 hours regardless
        of date parameters, so it's not suitable for backtesting.
        
        Pagination logic:
        - Start with before = end_ts + 1 day (to ensure we get end_date data)
        - Call get_history_candles with 'before' parameter
        - Update 'before' to oldest timestamp from each batch
        - Stop when oldest_timestamp <= start_ts
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Adjust end_date to yesterday if it's today (today's candles might not be complete)
        today = datetime.now().date()
        if end_dt.date() >= today:
            logger.info(f"   ⚠️  End date is today or future, adjusting to yesterday for complete candles")
            end_dt = datetime.now() - timedelta(days=1)
            end_dt = end_dt.replace(hour=23, minute=59, second=59)  # End of yesterday
        
        # Convert to milliseconds
        end_ts = int(end_dt.timestamp() * 1000)
        start_ts = int(start_dt.timestamp() * 1000)
        
        logger.info(f"   Adjusted date range: {start_date} to {end_dt.strftime('%Y-%m-%d')}")
        
        # CRITICAL FIX: Use 'after' parameter to paginate backwards (get older data)
        # OKX API: 'after' returns records OLDER than the timestamp
        # Strategy: Start with most recent data, then use 'after' to go backwards
        
        logger.info(f"   Fetching {timeframe} HISTORY data from {start_date} to {end_date}")
        logger.info(f"   Using history-candles endpoint with 'after' pagination (backwards)")
        logger.info(f"   Start timestamp: {datetime.fromtimestamp(start_ts/1000)}")
        logger.info(f"   End timestamp: {datetime.fromtimestamp(end_ts/1000)}")
        
        all_candles = []
        max_calls = 100  # Safety limit to prevent infinite loops
        call_count = 0
        
        # Strategy: First get most recent candles (without 'after'), then paginate backwards
        # This ensures we get data up to end_ts
        current_after = None  # Start with None to get most recent data first
        
        while call_count < max_calls:
            call_count += 1
            
            try:
                # First call: Get most recent candles (no 'after' parameter)
                # Subsequent calls: Use 'after' to get older candles
                # CRITICAL: Force history-candles endpoint for ALL backtesting calls
                if current_after is None:
                    logger.info(f"   Call {call_count}: Getting most recent candles (no 'after' parameter)")
                    logger.info(f"      This will get the latest available candles from OKX")
                    candles = self.client.get_history_candles(
                        symbol=symbol,
                        timeframe=timeframe,
                        after=None,  # No 'after' = get most recent
                        limit=100,
                        force_history_endpoint=True  # Force history endpoint for backtesting
                    )
                    
                    # If first call returns no data, try with regular candles endpoint as fallback
                    if (not candles or len(candles) == 0) and call_count == 1:
                        logger.warning(f"   ⚠️  First call returned no data, trying regular candles endpoint as fallback...")
                        candles_fallback = self.client.get_candles(
                            symbol=symbol,
                            timeframe=timeframe,
                            limit=100
                        )
                        if candles_fallback:
                            logger.info(f"   ✅ Fallback worked! Got {len(candles_fallback)} candles from regular endpoint")
                            candles = candles_fallback
                else:
                    logger.info(f"   Call {call_count}: Requesting candles after (older than) timestamp: {current_after} "
                               f"({datetime.fromtimestamp(current_after/1000)})")
                    candles = self.client.get_history_candles(
                        symbol=symbol,
                        timeframe=timeframe,
                        after=str(current_after),  # 'after' gets OLDER data
                        limit=100,  # history-candles max is 100
                        force_history_endpoint=True  # Force history endpoint for backtesting
                    )
                
                if not candles or len(candles) == 0:
                    if call_count == 1:
                        logger.error(f"   ❌ First API call returned ZERO candles!")
                        logger.error(f"      This suggests:")
                        logger.error(f"      1. API endpoint issue")
                        logger.error(f"      2. Symbol format issue (check: {symbol})")
                        logger.error(f"      3. Date range issue (dates might be too recent)")
                        logger.error(f"      4. OKX API might be down or rate-limited")
                    else:
                        logger.debug(f"   No more candles returned (call {call_count})")
                    break
                
                # Convert OKX format to our format
                # OKX returns candles in format: [timestamp, open, high, low, close, volume, ...]
                batch_candles = []
                for candle in candles:
                    ts = int(candle[0])
                    batch_candles.append({
                        'timestamp': ts,
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': float(candle[5])
                    })
                
                if not batch_candles:
                    logger.debug(f"   No candles in batch (call {call_count})")
                    break
                
                # Find oldest and newest timestamps in this batch
                oldest_ts = min(c['timestamp'] for c in batch_candles)
                newest_ts = max(c['timestamp'] for c in batch_candles)
                
                logger.info(f"   📥 Call {call_count}: Fetched {len(batch_candles)} candles "
                          f"({datetime.fromtimestamp(oldest_ts/1000).strftime('%Y-%m-%d %H:%M')} to "
                          f"{datetime.fromtimestamp(newest_ts/1000).strftime('%Y-%m-%d %H:%M')})")
                
                all_candles.extend(batch_candles)
                
                # Stop if we've reached or passed the start date
                if oldest_ts <= start_ts:
                    logger.info(f"   ✅ Reached start date ({start_date}), stopping pagination")
                    break
                
                # Move 'after' cursor to oldest timestamp for next iteration
                # This gets us even older candles in the next call (going backwards in time)
                current_after = oldest_ts
                
                # Rate limiting
                time.sleep(0.15)
                
                if call_count % 10 == 0:
                    logger.info(f"   Progress: Fetched {len(all_candles)} candles so far...")
                    
            except Exception as e:
                logger.error(f"   Error fetching candles (call {call_count}): {e}")
                import traceback
                logger.error(traceback.format_exc())
                break
        
        # Filter to requested date range (inclusive)
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
        
        logger.info(f"   ✅ Fetch complete: {len(unique_candles)} unique candles for {timeframe}")
        if unique_candles:
            first_ts = datetime.fromtimestamp(unique_candles[0]['timestamp'] / 1000)
            last_ts = datetime.fromtimestamp(unique_candles[-1]['timestamp'] / 1000)
            logger.info(f"   Data range: {first_ts.strftime('%Y-%m-%d %H:%M')} to {last_ts.strftime('%Y-%m-%d %H:%M')}")
        
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
    
    def load_from_binance_file(self, filepath: str, symbol_map: str = None) -> Dict:
        """
        Load historical data from downloaded Binance JSON file
        
        Args:
            filepath: Path to the Binance historical data JSON file
            symbol_map: How to map symbols (e.g., 'SOLUSDT' -> 'SOL-USDT-SWAP')
            
        Returns:
            Dict with timeframes as keys and candle lists as values
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            logger.error(f"❌ File not found: {filepath}")
            return {}
        
        logger.info(f"📂 Loading historical data from {filepath}")
        
        with open(filepath, 'r') as f:
            raw_data = json.load(f)
        
        # Extract metadata
        symbol = raw_data.get('symbol', 'UNKNOWN')
        start_date = raw_data.get('start_date', 'N/A')
        end_date = raw_data.get('end_date', 'N/A')
        candle_counts = raw_data.get('candle_counts', {})
        timeframes_data = raw_data.get('timeframes', {})
        
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Period: {start_date} to {end_date}")
        logger.info(f"   Candle counts: {candle_counts}")
        
        # Map timeframe names (Binance uses lowercase, we use mixed case)
        tf_mapping = {
            '5m': '5m',
            '15m': '15m',
            '1H': '1H',
            '1h': '1H',
            '4H': '4H', 
            '4h': '4H',
            '1D': '1D',
            '1d': '1D'
        }
        
        data = {}
        for tf_name, candles in timeframes_data.items():
            mapped_tf = tf_mapping.get(tf_name, tf_name)
            data[mapped_tf] = candles
            logger.info(f"   ✅ {mapped_tf}: {len(candles)} candles loaded")
        
        return data
    
    def load_extended_data(self, symbol: str, start_date: str, end_date: str,
                          binance_data_dir: str = "data/historical",
                          timeframes: Optional[List[str]] = None) -> Dict:
        """
        Load extended historical data - tries Binance files first, then OKX API
        
        This enables longer backtesting periods (6-12 months) by using
        pre-downloaded Binance data.
        
        Args:
            symbol: Trading symbol (e.g., 'SOL-USDT-SWAP')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            binance_data_dir: Directory containing downloaded Binance data
            timeframes: List of timeframes to load (default: all)
            
        Returns:
            Dict with timeframes as keys and candle lists as values
        """
        if timeframes is None:
            timeframes = list(self.timeframes.keys())
        
        binance_dir = Path(binance_data_dir)
        
        # Map OKX symbol to Binance symbol
        symbol_mapping = {
            'SOL-USDT-SWAP': 'SOLUSDT',
            'SOL-USDT': 'SOLUSDT',
            'BTC-USDT-SWAP': 'BTCUSDT',
            'BTC-USDT': 'BTCUSDT'
        }
        binance_symbol = symbol_mapping.get(symbol, symbol.replace('-', '').replace('SWAP', ''))
        
        # Look for Binance data files
        binance_files = list(binance_dir.glob(f"{binance_symbol}_*.json"))
        
        data = {}
        
        if binance_files:
            logger.info(f"📊 Found {len(binance_files)} Binance data file(s) for {symbol}")
            
            # Load from the most recent/comprehensive file
            # Sort by file size (larger = more data) or by date range in filename
            binance_files.sort(key=lambda x: x.stat().st_size, reverse=True)
            
            for bf in binance_files:
                binance_data = self.load_from_binance_file(bf)
                
                # Merge data (prioritize data with more candles)
                for tf, candles in binance_data.items():
                    if tf in timeframes:
                        if tf not in data or len(candles) > len(data.get(tf, [])):
                            data[tf] = candles
            
            # Filter data to requested date range
            start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            end_ts = int((datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).timestamp() * 1000)
            
            for tf in list(data.keys()):
                if data[tf]:
                    filtered = [c for c in data[tf] if start_ts <= c['timestamp'] <= end_ts]
                    data[tf] = filtered
                    logger.info(f"   {tf}: Filtered to {len(filtered)} candles in date range")
        
        # Fill in any missing timeframes from OKX API
        missing_tfs = [tf for tf in timeframes if tf not in data or not data[tf]]
        
        if missing_tfs:
            logger.info(f"   Fetching missing timeframes from OKX: {missing_tfs}")
            okx_data = self.load_data(symbol, start_date, end_date, timeframes=missing_tfs)
            
            for tf, candles in okx_data.items():
                if tf not in data or not data[tf]:
                    data[tf] = candles
        
        # Log summary
        logger.info(f"\n📊 Extended Data Loading Summary for {symbol}:")
        logger.info(f"   Requested Period: {start_date} to {end_date}")
        for tf, candles in data.items():
            if candles:
                first_ts = datetime.fromtimestamp(candles[0]['timestamp'] / 1000)
                last_ts = datetime.fromtimestamp(candles[-1]['timestamp'] / 1000)
                logger.info(f"   {tf}: {len(candles)} candles")
                logger.info(f"      Date Range: {first_ts.strftime('%Y-%m-%d %H:%M')} to {last_ts.strftime('%Y-%m-%d %H:%M')}")
            else:
                logger.warning(f"   {tf}: NO DATA")
        
        return data
