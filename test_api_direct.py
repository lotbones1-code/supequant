#!/usr/bin/env python3
"""Quick test to see what OKX API is actually returning"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data_feed.okx_client import OKXClient

print("Testing OKX API directly...\n")

client = OKXClient()

# Test 1: Simple get_candles (recent data)
print("1. Testing get_candles (recent):")
result1 = client.get_candles('SOL-USDT-SWAP', '15m', limit=5)
print(f"   Result: {result1}\n")

# Test 2: get_history_candles without parameters
print("2. Testing get_history_candles (no params):")
result2 = client.get_history_candles('SOL-USDT-SWAP', '15m', limit=5)
print(f"   Result: {result2}\n")

# Test 3: get_history_candles with before parameter
print("3. Testing get_history_candles (with before param):")
# Nov 25, 2024 timestamp
before_ts = "1732492800000"
result3 = client.get_history_candles('SOL-USDT-SWAP', '15m', limit=5, before=before_ts)
print(f"   Result: {result3}\n")

print("Done!")
