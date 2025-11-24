#!/usr/bin/env python3
"""
Test OKX history-candles endpoint directly
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data_feed.okx_client import OKXClient
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

client = OKXClient()

print("\n" + "="*80)
print("TESTING OKX HISTORY-CANDLES ENDPOINT")
print("="*80)

# Test 1: Without any pagination parameters
print("\n1️⃣  Test: history-candles WITHOUT before/after parameters")
print("   Calling: get_history_candles('SOL-USDT-SWAP', '15m', limit=10)")

candles = client.get_history_candles(
    symbol='SOL-USDT-SWAP',
    timeframe='15m',
    limit=10
)

if candles:
    print(f"   ✅ SUCCESS! Got {len(candles)} candles")
    if candles:
        print(f"   Latest candle timestamp: {candles[0][0]}")
else:
    print("   ❌ FAILED")

# Test 2: With before parameter
print("\n2️⃣  Test: history-candles WITH before parameter")
print("   Using timestamp: 1732924800000 (Nov 30, 2024)")

candles2 = client.get_history_candles(
    symbol='SOL-USDT-SWAP',
    timeframe='15m',
    limit=10,
    before='1732924800000'
)

if candles2:
    print(f"   ✅ SUCCESS! Got {len(candles2)} candles")
else:
    print("   ❌ FAILED with before parameter")

# Test 3: Regular candles endpoint for comparison
print("\n3️⃣  Test: regular candles endpoint (for comparison)")

candles3 = client.get_candles(
    symbol='SOL-USDT-SWAP',
    timeframe='15m',
    limit=10
)

if candles3:
    print(f"   ✅ SUCCESS! Got {len(candles3)} candles from regular endpoint")
else:
    print("   ❌ FAILED")

print("\n" + "="*80)
