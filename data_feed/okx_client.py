"""
OKX Client - Backward Compatibility Shim

This file re-exports HyperliquidClient as OKXClient so that ALL existing
imports (`from data_feed.okx_client import OKXClient`) continue to work
without modification.

The original OKX implementation is preserved in okx_client_legacy.py.
"""

from .hyperliquid_client import HyperliquidClient as OKXClient

__all__ = ['OKXClient']
