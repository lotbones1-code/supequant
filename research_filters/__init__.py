"""
Research Filters Module
Custom filters based on trading research and playbooks
These encode manual trading rules into automated checks

Components:
- SOLPlaybookEngine: Discretionary playbook → systematic rules
- TradingChecklistFilter: Manual checklist → automated scoring (0-100)
- DriverTierWeighting: 4-tier macro analysis → unified assessment
"""

from .sol_playbook import SOLPlaybookEngine
from .checklist_filter import TradingChecklistFilter
from .driver_weighting import DriverTierWeighting

__all__ = ['SOLPlaybookEngine', 'TradingChecklistFilter', 'DriverTierWeighting']
