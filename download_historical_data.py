"""
Download Extended Historical Data from Binance for Backtesting

This script downloads 6-12 months of historical data for SOL and BTC
to enable longer backtesting periods.

Usage:
    python download_historical_data.py --months 12
    python download_historical_data.py --start 2025-01-01 --end 2026-01-15
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from superquant.data.binance_client import BinanceFuturesClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HistoricalDataDownloader:
    """Download extended historical data from Binance"""
    
    def __init__(self, output_dir: str = "data/historical"):
        self.client = BinanceFuturesClient(venue="mainnet")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Timeframe mapping (Binance format)
        self.timeframes = {
            '5m': '5m',
            '15m': '15m', 
            '1H': '1h',
            '4H': '4h',
            '1D': '1d'
        }
        
        logger.info(f"📂 Output directory: {self.output_dir}")
    
    def download_klines_paginated(self, symbol: str, interval: str, 
                                   start_date: datetime, end_date: datetime) -> list:
        """
        Download klines with pagination (Binance returns max 1500 per request)
        
        Args:
            symbol: e.g. 'SOLUSDT'
            interval: e.g. '15m', '1h', '4h'
            start_date: Start datetime
            end_date: End datetime
            
        Returns:
            List of all klines
        """
        all_klines = []
        current_start = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        
        # Calculate interval in milliseconds for pagination
        interval_ms = {
            '1m': 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000
        }.get(interval, 15 * 60 * 1000)
        
        batch_size = 1500
        batch_duration_ms = batch_size * interval_ms
        
        logger.info(f"📥 Downloading {symbol} {interval} from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        request_count = 0
        while current_start < end_ts:
            batch_end = min(current_start + batch_duration_ms, end_ts)
            
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                end_time=batch_end,
                limit=1500
            )
            
            if not klines:
                logger.warning(f"   No data returned for batch starting {datetime.fromtimestamp(current_start/1000)}")
                current_start = batch_end + interval_ms
                continue
            
            all_klines.extend(klines)
            request_count += 1
            
            # Move to next batch (start from last candle + 1 interval)
            if klines:
                current_start = klines[-1]['timestamp'] + interval_ms
            else:
                current_start = batch_end + interval_ms
            
            # Progress update every 10 requests
            if request_count % 10 == 0:
                progress = (current_start - int(start_date.timestamp() * 1000)) / (end_ts - int(start_date.timestamp() * 1000)) * 100
                logger.info(f"   Progress: {progress:.1f}% ({len(all_klines)} candles)")
            
            # Rate limiting - be gentle with the API
            time.sleep(0.1)
        
        # Remove duplicates (by timestamp)
        seen = set()
        unique_klines = []
        for k in all_klines:
            if k['timestamp'] not in seen:
                seen.add(k['timestamp'])
                unique_klines.append(k)
        
        # Sort by timestamp
        unique_klines.sort(key=lambda x: x['timestamp'])
        
        logger.info(f"   ✅ Downloaded {len(unique_klines)} candles for {symbol} {interval}")
        return unique_klines
    
    def download_symbol(self, symbol: str, start_date: datetime, end_date: datetime):
        """Download all timeframes for a symbol"""
        
        symbol_data = {}
        
        for tf_name, binance_interval in self.timeframes.items():
            try:
                klines = self.download_klines_paginated(symbol, binance_interval, start_date, end_date)
                symbol_data[tf_name] = klines
            except Exception as e:
                logger.error(f"❌ Error downloading {symbol} {tf_name}: {e}")
                symbol_data[tf_name] = []
        
        return symbol_data
    
    def save_data(self, data: dict, symbol: str, start_date: datetime, end_date: datetime):
        """Save downloaded data to JSON file"""
        
        filename = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
        filepath = self.output_dir / filename
        
        # Add metadata
        output = {
            'symbol': symbol,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'downloaded_at': datetime.now().isoformat(),
            'timeframes': data,
            'candle_counts': {tf: len(candles) for tf, candles in data.items()}
        }
        
        with open(filepath, 'w') as f:
            json.dump(output, f)
        
        logger.info(f"💾 Saved {filepath}")
        logger.info(f"   Candle counts: {output['candle_counts']}")
        
        return filepath
    
    def download_all(self, start_date: datetime, end_date: datetime, 
                     symbols: list = ['SOLUSDT', 'BTCUSDT']):
        """Download data for all symbols"""
        
        logger.info("=" * 60)
        logger.info("🚀 STARTING HISTORICAL DATA DOWNLOAD")
        logger.info("=" * 60)
        logger.info(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        logger.info(f"Symbols: {symbols}")
        logger.info(f"Timeframes: {list(self.timeframes.keys())}")
        logger.info("=" * 60)
        
        saved_files = []
        
        for symbol in symbols:
            logger.info(f"\n📊 Downloading {symbol}...")
            data = self.download_symbol(symbol, start_date, end_date)
            filepath = self.save_data(data, symbol, start_date, end_date)
            saved_files.append(filepath)
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ DOWNLOAD COMPLETE")
        logger.info("=" * 60)
        logger.info("Saved files:")
        for f in saved_files:
            logger.info(f"   {f}")
        
        return saved_files


def main():
    parser = argparse.ArgumentParser(description='Download historical data from Binance')
    
    parser.add_argument('--months', type=int, default=None,
                       help='Number of months to download (from today backwards)')
    parser.add_argument('--start', type=str, default=None,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--symbols', type=str, nargs='+', 
                       default=['SOLUSDT', 'BTCUSDT'],
                       help='Symbols to download')
    parser.add_argument('--output', type=str, default='data/historical',
                       help='Output directory')
    
    args = parser.parse_args()
    
    # Determine date range
    if args.months:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.months * 30)
    elif args.start and args.end:
        start_date = datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d')
    else:
        # Default: 12 months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
    
    # Download
    downloader = HistoricalDataDownloader(output_dir=args.output)
    downloader.download_all(start_date, end_date, args.symbols)


if __name__ == '__main__':
    main()
