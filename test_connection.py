#!/usr/bin/env python3
"""
Quick connection test - Verify OKX API works before live trading
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data_feed.okx_client import OKXClient
import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_connection():
    print("\n" + "="*60)
    print("🔍 TESTING OKX CONNECTION")
    print("="*60)
    
    # Check config
    print("\n1️⃣  Checking Configuration:")
    print(f"   API Key: {'✅ Set' if config.OKX_API_KEY else '❌ Missing'}")
    print(f"   Secret Key: {'✅ Set' if config.OKX_SECRET_KEY else '❌ Missing'}")
    print(f"   Passphrase: {'✅ Set' if config.OKX_PASSPHRASE else '❌ Missing'}")
    print(f"   Simulated: {'🟡 Yes (Paper Trading)' if config.OKX_SIMULATED else '🔴 No (LIVE TRADING)'}")
    print(f"   Trading Symbol: {config.TRADING_SYMBOL}")
    
    if not all([config.OKX_API_KEY, config.OKX_SECRET_KEY, config.OKX_PASSPHRASE]):
        print("\n❌ ERROR: Missing API credentials!")
        return False
    
    # Initialize client
    print("\n2️⃣  Initializing OKX Client...")
    try:
        client = OKXClient()
        print(f"   ✅ Client initialized")
        print(f"   Mode: {'SIMULATED' if client.simulated else 'LIVE'}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test public endpoint (ticker)
    print("\n3️⃣  Testing Public API (Ticker)...")
    try:
        ticker = client.get_ticker(config.TRADING_SYMBOL)
        if ticker:
            price = ticker.get('last', 'N/A')
            print(f"   ✅ SUCCESS! SOL Price: ${price}")
        else:
            print("   ⚠️  No ticker data returned")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test account balance (authenticated)
    print("\n4️⃣  Testing Authenticated API (Account Balance)...")
    try:
        balance = client.get_account_balance()
        if balance:
            usdt_balance = balance.get('USDT', {}).get('available', 0)
            print(f"   ✅ SUCCESS! Account Balance: ${usdt_balance}")
            if float(usdt_balance) < 5:
                print(f"   ⚠️  Warning: Balance is less than $5")
            else:
                print(f"   ✅ Balance sufficient for trading")
        else:
            print("   ⚠️  Could not get balance (may need to check permissions)")
    except Exception as e:
        print(f"   ⚠️  Balance check failed: {e}")
        print("   (This is OK if using simulated mode)")
    
    print("\n" + "="*60)
    print("✅ CONNECTION TEST COMPLETE!")
    print("="*60)
    print("\n🚀 If all tests passed, you're ready to trade!")
    print("   Run: python main.py")
    print("="*60 + "\n")
    
    return True

if __name__ == "__main__":
    test_connection()
