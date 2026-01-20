#!/usr/bin/env python3
"""
Quick OKX API Test
Tests if the OKX API is responding properly

Usage:
    python test_okx_api.py
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data_feed.okx_client import OKXClient
import config

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_okx_api():
    """Test basic OKX API functionality"""

    print("\n" + "="*80)
    print("OKX API CONNECTION TEST")
    print("="*80)

    # Initialize client
    print("\n1️⃣  Initializing OKX Client...")
    client = OKXClient()
    print(f"   Base URL: {client.base_url}")
    print(f"   Simulated Mode: {client.simulated}")
    print(f"   API Key Set: {'✅' if client.api_key else '❌'}")
    print(f"   Secret Key Set: {'✅' if client.secret_key else '❌'}")
    print(f"   Passphrase Set: {'✅' if client.passphrase else '❌'}")

    if not (client.api_key and client.secret_key and client.passphrase):
        print("\n❌ ERROR: API credentials not set in .env file!")
        print("   Please add:")
        print("   OKX_API_KEY=your_key_here")
        print("   OKX_SECRET_KEY=your_secret_here")
        print("   OKX_PASSPHRASE=your_passphrase_here")
        return False

    # Test 1: Get ticker (simple public endpoint)
    print("\n2️⃣  Testing ticker endpoint (public)...")
    symbol = config.TRADING_SYMBOL
    print(f"   Symbol: {symbol}")

    ticker = client.get_ticker(symbol)
    if ticker:
        print(f"   ✅ SUCCESS! Got ticker data:")
        print(f"      Last Price: ${ticker.get('last', 'N/A')}")
        print(f"      24h High: ${ticker.get('high24h', 'N/A')}")
        print(f"      24h Low: ${ticker.get('low24h', 'N/A')}")
    else:
        print(f"   ❌ FAILED: Could not get ticker")
        print(f"   Possible issues:")
        print(f"      - Symbol format wrong (try: SOL-USDT-SWAP vs SOL-USDT)")
        print(f"      - API keys invalid")
        print(f"      - Network/firewall blocking OKX")
        return False

    # Test 2: Get recent candles
    print("\n3️⃣  Testing candles endpoint...")
    print(f"   Symbol: {symbol}")
    print(f"   Timeframe: 15m")
    print(f"   Limit: 10 candles")

    candles = client.get_candles(
        symbol=symbol,
        timeframe='15m',
        limit=10
    )

    if candles:
        print(f"   ✅ SUCCESS! Got {len(candles)} candles")
        if len(candles) > 0:
            latest = candles[0]  # OKX returns newest first
            print(f"      Latest candle:")
            print(f"         Time: {latest[0]}")
            print(f"         Open: ${latest[1]}")
            print(f"         High: ${latest[2]}")
            print(f"         Low: ${latest[3]}")
            print(f"         Close: ${latest[4]}")
            print(f"         Volume: {latest[5]}")
    else:
        print(f"   ❌ FAILED: Could not get candles")
        print(f"   Check logs above for error details")
        return False

    # Test 3: Try different symbol formats
    print("\n4️⃣  Testing different symbol formats...")
    test_symbols = [
        'SOL-USDT-SWAP',  # Perpetual swap
        'SOL-USDT',       # Spot
        'SOL-USD-SWAP',   # USD-settled swap
    ]

    for test_symbol in test_symbols:
        print(f"\n   Testing: {test_symbol}")
        test_ticker = client.get_ticker(test_symbol)
        if test_ticker:
            print(f"      ✅ {test_symbol} works! Last: ${test_ticker.get('last', 'N/A')}")
        else:
            print(f"      ❌ {test_symbol} failed")

    print("\n" + "="*80)
    print("✅ OKX API TEST COMPLETE")
    print("="*80)
    print("\nIf all tests passed, the API is working correctly.")
    print("If tests failed, check:")
    print("  1. .env file has correct OKX API credentials")
    print("  2. Symbol format (try different formats above)")
    print("  3. Network connectivity to OKX")
    print("  4. API keys have correct permissions")
    print("="*80 + "\n")

    return True


if __name__ == '__main__':
    try:
        success = test_okx_api()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
