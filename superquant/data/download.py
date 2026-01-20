"""
CLI tool for downloading Binance USD-M Futures data
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import yaml

from .binance_client import BinanceFuturesClient
from .data_store import DataStore

logger = logging.getLogger(__name__)


def parse_config(config_path: str) -> dict:
    """
    Parse YAML config file
    
    Args:
        config_path: Path to config.yaml
    
    Returns:
        Config dict
    """
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def download_date_range(client: BinanceFuturesClient, store: DataStore,
                       symbol: str, interval: str, start_date: str, end_date: str,
                       data_types: list = ['klines', 'mark_price', 'funding_rate']):
    """
    Download data for a date range
    
    Args:
        client: Binance client
        store: Data store
        symbol: Trading symbol
        interval: Time interval (for klines/mark_price)
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        data_types: List of data types to download
    """
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Convert dates to timestamps
    start_ts = int(start.timestamp() * 1000)
    end_ts = int((end + timedelta(days=1)).timestamp() * 1000) - 1
    
    logger.info(f"📥 Downloading {symbol} data from {start_date} to {end_date}")
    logger.info(f"   Interval: {interval}")
    logger.info(f"   Data types: {', '.join(data_types)}")
    
    # Download klines
    if 'klines' in data_types:
        logger.info(f"📊 Downloading klines...")
        klines = client.get_klines(symbol, interval, start_ts, end_ts, limit=1500)
        
        if klines:
            # Group by date and save
            current_date = start
            while current_date <= end:
                date_str = current_date.strftime('%Y-%m-%d')
                date_start_ts = int(current_date.timestamp() * 1000)
                date_end_ts = int((current_date + timedelta(days=1)).timestamp() * 1000) - 1
                
                date_klines = [k for k in klines if date_start_ts <= k['timestamp'] < date_end_ts]
                if date_klines:
                    store.save_klines(date_klines, symbol, interval, date_str)
                
                current_date += timedelta(days=1)
    
    # Download mark price klines
    if 'mark_price' in data_types:
        logger.info(f"📊 Downloading mark price klines...")
        mark_klines = client.get_mark_price_klines(symbol, interval, start_ts, end_ts, limit=1500)
        
        if mark_klines:
            current_date = start
            while current_date <= end:
                date_str = current_date.strftime('%Y-%m-%d')
                date_start_ts = int(current_date.timestamp() * 1000)
                date_end_ts = int((current_date + timedelta(days=1)).timestamp() * 1000) - 1
                
                date_klines = [k for k in mark_klines if date_start_ts <= k['timestamp'] < date_end_ts]
                if date_klines:
                    store.save_mark_price_klines(date_klines, symbol, interval, date_str)
                
                current_date += timedelta(days=1)
    
    # Download funding rates
    if 'funding_rate' in data_types:
        logger.info(f"📊 Downloading funding rates...")
        funding_rates = client.get_funding_rate(symbol, start_ts, end_ts, limit=1000)
        
        if funding_rates:
            current_date = start
            while current_date <= end:
                date_str = current_date.strftime('%Y-%m-%d')
                date_start_ts = int(current_date.timestamp() * 1000)
                date_end_ts = int((current_date + timedelta(days=1)).timestamp() * 1000) - 1
                
                date_rates = [r for r in funding_rates if date_start_ts <= r['funding_time'] < date_end_ts]
                if date_rates:
                    store.save_funding_rates(date_rates, symbol, date_str)
                
                current_date += timedelta(days=1)
    
    logger.info(f"✅ Download complete for {symbol}")


def main() -> int:
    """Main CLI entry point
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description='Download Binance USD-M Futures data',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--config', type=str, default='config.yaml',
                       help='Path to config.yaml file')
    parser.add_argument('--start', type=str, required=True,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--symbols', type=str, nargs='+',
                       default=['SOLUSDT', 'BTCUSDT'],
                       help='Trading symbols (default: SOLUSDT BTCUSDT)')
    parser.add_argument('--intervals', type=str, nargs='+',
                       default=['1m', '5m', '15m', '1h', '4h', '1d'],
                       help='Time intervals (default: 1m 5m 15m 1h 4h 1d)')
    parser.add_argument('--data-types', type=str, nargs='+',
                       default=['klines', 'mark_price', 'funding_rate'],
                       help='Data types to download')
    parser.add_argument('--data-dir', type=str, default='data/binance',
                       help='Data storage directory')
    parser.add_argument('--verbose', action='store_true',
                       help='Verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Load config
    config = {}
    if Path(args.config).exists():
        config = parse_config(args.config)
        logger.info(f"📄 Loaded config from {args.config}")
    else:
        logger.warning(f"⚠️  Config file not found: {args.config}, using defaults")
    
    # Initialize client and store
    api_key = config.get('binance', {}).get('api_key')
    api_secret = config.get('binance', {}).get('api_secret')
    
    client = BinanceFuturesClient(api_key=api_key, api_secret=api_secret)
    store = DataStore(base_dir=args.data_dir)
    
    # Download data for each symbol and interval
    for symbol in args.symbols:
        for interval in args.intervals:
            try:
                download_date_range(
                    client, store, symbol, interval,
                    args.start, args.end, args.data_types
                )
            except Exception as e:
                logger.error(f"❌ Error downloading {symbol} {interval}: {e}", exc_info=True)
    
    logger.info("🎉 All downloads complete!")
    return 0


if __name__ == '__main__':
    main()

