"""
Data Feed Module
Handles all market data acquisition from exchange API and on-chain sources
"""

from .hyperliquid_client import HyperliquidClient as OKXClient  # Alias for compatibility
from .market_data import MarketDataFeed
from .indicators import TechnicalIndicators
from .onchain_tracker import OnchainTracker
from .liquidation_tracker import LiquidationTracker
from .sentiment_tracker import SentimentTracker, get_sentiment_tracker
from .market_structure import MarketStructureAnalyzer

__all__ = [
    'OKXClient',  # Now points to HyperliquidClient
    'MarketDataFeed',
    'TechnicalIndicators',
    'OnchainTracker',
    'LiquidationTracker',
    'SentimentTracker',
    'get_sentiment_tracker',
    'MarketStructureAnalyzer'
]
