#!/usr/bin/env python3
"""
Test balance fetching - debug OKX balance response
"""

import sys
import logging
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from data_feed.okx_client import OKXClient
import config

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_balance():
    """Test balance fetching"""
    print("\n" + "="*80)
    print("OKX BALANCE TEST")
    print("="*80)

    # Initialize client
    print("\n1️⃣  Initializing OKX Client...")
    client = OKXClient()
    print(f"   Base URL: {client.base_url}")
    print(f"   Simulated Mode: {client.simulated}")
    print(f"   Dry Run: {client.dry_run}")
    print(f"   API Key Set: {'✅' if client.api_key else '❌'}")
    print(f"   Secret Key Set: {'✅' if client.secret_key else '❌'}")
    print(f"   Passphrase Set: {'✅' if client.passphrase else '❌'}")

    if not (client.api_key and client.secret_key and client.passphrase):
        print("\n❌ ERROR: API credentials not set!")
        return False

    # Test balance fetch
    print("\n2️⃣  Fetching account balance...")
    balance_data = client.get_account_balance()
    
    if balance_data:
        print(f"\n✅ SUCCESS! Got balance data:")
        print(json.dumps(balance_data, indent=2))
        
        # Try to parse USDT balance
        print("\n3️⃣  Parsing USDT balance...")
        for balance in balance_data:
            details = balance.get('details', [])
            print(f"   Found {len(details)} detail(s)")
            for detail in details:
                ccy = detail.get('ccy', 'UNKNOWN')
                avail_eq = detail.get('availEq', 'N/A')
                eq = detail.get('eq', 'N/A')
                print(f"   Currency: {ccy}")
                print(f"   availEq: '{avail_eq}' (type: {type(avail_eq).__name__})")
                print(f"   eq: '{eq}' (type: {type(eq).__name__})")
                
                if ccy == 'USDT':
                    try:
                        if avail_eq == '' or avail_eq is None:
                            print(f"   ⚠️  availEq is empty, using 0")
                            avail_eq = '0'
                        balance_value = float(avail_eq)
                        print(f"   ✅ Parsed balance: ${balance_value:.2f}")
                    except ValueError as e:
                        print(f"   ❌ Error parsing: {e}")
    else:
        print("\n❌ FAILED: No balance data returned")
        return False

    print("\n" + "="*80)
    return True

if __name__ == '__main__':
    test_balance()
