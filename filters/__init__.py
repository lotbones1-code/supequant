"""
Filters Module
All trade filtering logic - prevents bad trades from executing
Every filter must pass before a trade is allowed
"""

from .market_regime import MarketRegimeFilter
from .market_regime_enhanced import MarketRegimeEnhancedFilter
from .multi_timeframe import MultiTimeframeFilter
from .ai_rejection import AIRejectionFilter
from .pattern_failure import PatternFailureFilter
from .btc_sol_correlation import BTCSOLCorrelationFilter
from .macro_driver import MacroDriverFilter
from .time_of_day import TimeOfDayFilter
from .funding_rate import FundingRateFilter
from .whale_filter import WhaleFilter
from .liquidation_filter import LiquidationFilter
from .open_interest import OpenInterestFilter
from .filter_manager import FilterManager

__all__ = [
    'MarketRegimeFilter',
    'MarketRegimeEnhancedFilter',
    'MultiTimeframeFilter',
    'AIRejectionFilter',
    'PatternFailureFilter',
    'BTCSOLCorrelationFilter',
    'MacroDriverFilter',
    'TimeOfDayFilter',
    'FundingRateFilter',
    'WhaleFilter',
    'LiquidationFilter',
    'OpenInterestFilter',
    'FilterManager'
]
