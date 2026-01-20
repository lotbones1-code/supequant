#!/usr/bin/env python3
"""
Test passphrase - verify it's being read correctly
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

passphrase = os.getenv('OKX_PASSPHRASE', '')
api_key = os.getenv('OKX_API_KEY', '')
secret_key = os.getenv('OKX_SECRET_KEY', '')

print("="*60)
print("PASSPHRASE VERIFICATION")
print("="*60)
print(f"\nPassphrase from .env: '{passphrase}'")
print(f"Passphrase length: {len(passphrase)}")
print(f"Passphrase repr: {repr(passphrase)}")
print(f"\nExpected: 'Stcuk567@'")
print(f"Matches: {'✅ YES' if passphrase.strip() == 'Stcuk567@' else '❌ NO'}")
print(f"\nAPI Key: {api_key[:20]}...")
print(f"Secret Key: {secret_key[:10]}...")
print("\n" + "="*60)
print("\n⚠️  IMPORTANT: Make sure the passphrase in OKX matches EXACTLY:")
print("   'Stcuk567@' (with capital S, lowercase tcuk, numbers 567, @ symbol)")
print("\nIf it doesn't match, either:")
print("   1. Update .env file with correct passphrase")
print("   2. Or update OKX API key passphrase to match")
print("="*60)
