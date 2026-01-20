"""
Data Store
Persists market data to Parquet files with deterministic schema
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class DataStore:
    """
    Stores market data to Parquet files with deterministic schema
    
    Features:
    - Deterministic schema for all data types
    - Partitioned by symbol and date
    - Timestamp alignment validation
    - Missing interval detection
    """
    
    # Deterministic schemas
    KLINES_SCHEMA = pa.schema([
        pa.field('timestamp', pa.int64(), nullable=False),
        pa.field('open', pa.float64(), nullable=False),
        pa.field('high', pa.float64(), nullable=False),
        pa.field('low', pa.float64(), nullable=False),
        pa.field('close', pa.float64(), nullable=False),
        pa.field('volume', pa.float64(), nullable=False),
        pa.field('close_time', pa.int64(), nullable=False),
        pa.field('quote_volume', pa.float64(), nullable=False),
        pa.field('trades', pa.int64(), nullable=False),
        pa.field('taker_buy_base_volume', pa.float64(), nullable=False),
        pa.field('taker_buy_quote_volume', pa.float64(), nullable=False),
        pa.field('ignore', pa.int64(), nullable=False),
        pa.field('symbol', pa.string(), nullable=False),
        pa.field('interval', pa.string(), nullable=False),
    ])
    
    MARK_PRICE_SCHEMA = pa.schema([
        pa.field('timestamp', pa.int64(), nullable=False),
        pa.field('mark_price', pa.float64(), nullable=False),
        pa.field('close', pa.float64(), nullable=False),
        pa.field('symbol', pa.string(), nullable=False),
        pa.field('interval', pa.string(), nullable=False),
    ])
    
    FUNDING_RATE_SCHEMA = pa.schema([
        pa.field('symbol', pa.string(), nullable=False),
        pa.field('funding_time', pa.int64(), nullable=False),
        pa.field('funding_rate', pa.float64(), nullable=False),
        pa.field('mark_price', pa.float64(), nullable=False),
    ])
    
    def __init__(self, base_dir: str = "data/binance"):
        """
        Initialize data store
        
        Args:
            base_dir: Base directory for data storage
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✅ DataStore initialized: {self.base_dir}")

    def _get_file_path(self, data_type: str, symbol: str, interval: Optional[str] = None,
                      date: Optional[str] = None) -> Path:
        """
        Get file path for data
        
        Args:
            data_type: 'klines', 'mark_price', or 'funding_rate'
            symbol: Trading symbol
            interval: Time interval (for klines/mark_price)
            date: Date string YYYY-MM-DD (for partitioning)
        
        Returns:
            Path to data file
        """
        if date:
            # Partitioned by date
            date_path = self.base_dir / data_type / symbol / date[:4] / date[5:7] / date[8:10]
        else:
            # Not partitioned
            date_path = self.base_dir / data_type / symbol
        
        date_path.mkdir(parents=True, exist_ok=True)
        
        if interval:
            filename = f"{symbol}_{interval}_{date or 'all'}.parquet"
        else:
            filename = f"{symbol}_{date or 'all'}.parquet"
        
        return date_path / filename

    def save_klines(self, klines: List[Dict], symbol: str, interval: str,
                   date: Optional[str] = None) -> Path:
        """
        Save klines to Parquet
        
        Args:
            klines: List of kline dicts
            symbol: Trading symbol
            interval: Time interval
            date: Date string for partitioning (YYYY-MM-DD)
        
        Returns:
            Path to saved file
        """
        if not klines:
            logger.warning(f"No klines to save for {symbol} {interval}")
            return None
        
        # Add symbol and interval to each record
        for k in klines:
            k['symbol'] = symbol
            k['interval'] = interval
        
        df = pd.DataFrame(klines)
        
        # Ensure timestamp is int64
        df['timestamp'] = df['timestamp'].astype('int64')
        df['close_time'] = df['close_time'].astype('int64')
        df['trades'] = df['trades'].astype('int64')
        df['ignore'] = df['ignore'].astype('int64')
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Convert to PyArrow table with schema
        table = pa.Table.from_pandas(df, schema=self.KLINES_SCHEMA)
        
        # Get file path
        file_path = self._get_file_path('klines', symbol, interval, date)
        
        # Write to Parquet
        pq.write_table(table, file_path, compression='snappy')
        
        logger.info(f"💾 Saved {len(klines)} klines to {file_path}")
        return file_path

    def save_mark_price_klines(self, klines: List[Dict], symbol: str, interval: str,
                               date: Optional[str] = None) -> Path:
        """
        Save mark price klines to Parquet
        
        Args:
            klines: List of mark price kline dicts
            symbol: Trading symbol
            interval: Time interval
            date: Date string for partitioning
        
        Returns:
            Path to saved file
        """
        if not klines:
            logger.warning(f"No mark price klines to save for {symbol} {interval}")
            return None
        
        # Add symbol and interval
        for k in klines:
            k['symbol'] = symbol
            k['interval'] = interval
        
        df = pd.DataFrame(klines)
        df['timestamp'] = df['timestamp'].astype('int64')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        table = pa.Table.from_pandas(df, schema=self.MARK_PRICE_SCHEMA)
        
        file_path = self._get_file_path('mark_price', symbol, interval, date)
        pq.write_table(table, file_path, compression='snappy')
        
        logger.info(f"💾 Saved {len(klines)} mark price klines to {file_path}")
        return file_path

    def save_funding_rates(self, rates: List[Dict], symbol: str,
                          date: Optional[str] = None) -> Path:
        """
        Save funding rates to Parquet
        
        Args:
            rates: List of funding rate dicts
            symbol: Trading symbol
            date: Date string for partitioning
        
        Returns:
            Path to saved file
        """
        if not rates:
            logger.warning(f"No funding rates to save for {symbol}")
            return None
        
        df = pd.DataFrame(rates)
        df['funding_time'] = df['funding_time'].astype('int64')
        df = df.sort_values('funding_time').reset_index(drop=True)
        
        table = pa.Table.from_pandas(df, schema=self.FUNDING_RATE_SCHEMA)
        
        file_path = self._get_file_path('funding_rate', symbol, date=date)
        pq.write_table(table, file_path, compression='snappy')
        
        logger.info(f"💾 Saved {len(rates)} funding rates to {file_path}")
        return file_path

    def load_klines(self, symbol: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Load klines for date range
        
        Args:
            symbol: Trading symbol
            interval: Time interval
            start_date: Start date YYYY-MM-DD
            end_date: End date YYYY-MM-DD
        
        Returns:
            DataFrame with klines
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        dfs = []
        current = start
        
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            file_path = self._get_file_path('klines', symbol, interval, date_str)
            
            if file_path.exists():
                df = pd.read_parquet(file_path)
                dfs.append(df)
            
            current += timedelta(days=1)
        
        if not dfs:
            return pd.DataFrame()
        
        result = pd.concat(dfs, ignore_index=True)
        result = result.sort_values('timestamp').reset_index(drop=True)
        
        # Remove duplicates
        result = result.drop_duplicates(subset=['timestamp'], keep='first')
        
        return result

    def validate_timestamp_alignment(self, sol_df: pd.DataFrame, btc_df: pd.DataFrame,
                                    interval: str) -> Dict:
        """
        Validate timestamp alignment between SOL and BTC
        
        Args:
            sol_df: SOL klines DataFrame
            btc_df: BTC klines DataFrame
            interval: Time interval
        
        Returns:
            Validation results dict
        """
        if sol_df.empty or btc_df.empty:
            return {
                'valid': False,
                'error': 'Empty dataframes'
            }
        
        sol_timestamps = set(sol_df['timestamp'].values)
        btc_timestamps = set(btc_df['timestamp'].values)
        
        # Find missing timestamps
        missing_in_btc = sol_timestamps - btc_timestamps
        missing_in_sol = btc_timestamps - sol_timestamps
        common = sol_timestamps & btc_timestamps
        
        # Calculate interval in milliseconds
        interval_ms = self._interval_to_ms(interval)
        
        # Check for gaps
        sol_gaps = self._find_gaps(sol_df['timestamp'].values, interval_ms)
        btc_gaps = self._find_gaps(btc_df['timestamp'].values, interval_ms)
        
        return {
            'valid': len(missing_in_btc) == 0 and len(missing_in_sol) == 0 and len(sol_gaps) == 0 and len(btc_gaps) == 0,
            'common_timestamps': len(common),
            'missing_in_btc': len(missing_in_btc),
            'missing_in_sol': len(missing_in_sol),
            'sol_gaps': len(sol_gaps),
            'btc_gaps': len(btc_gaps),
            'sol_gap_details': sol_gaps[:10],  # First 10 gaps
            'btc_gap_details': btc_gaps[:10],
        }

    def _interval_to_ms(self, interval: str) -> int:
        """Convert interval string to milliseconds"""
        multipliers = {
            'm': 60 * 1000,
            'h': 60 * 60 * 1000,
            'd': 24 * 60 * 60 * 1000,
            'w': 7 * 24 * 60 * 60 * 1000,
        }
        
        unit = interval[-1]
        value = int(interval[:-1])
        
        return value * multipliers.get(unit, 0)

    def _find_gaps(self, timestamps: List[int], interval_ms: int) -> List[Dict]:
        """Find gaps in timestamp sequence"""
        gaps = []
        sorted_ts = sorted(timestamps)
        
        for i in range(len(sorted_ts) - 1):
            expected_next = sorted_ts[i] + interval_ms
            actual_next = sorted_ts[i + 1]
            
            if actual_next > expected_next:
                gaps.append({
                    'from': sorted_ts[i],
                    'to': sorted_ts[i + 1],
                    'expected': expected_next,
                    'missing_intervals': (actual_next - expected_next) // interval_ms
                })
        
        return gaps

