# -*- coding: utf-8 -*-
"""
Scope parser for natural-language queries.

Parses phrases like:
    "why did we lose 7d"
    "why did we lose last 20 trades"
    "why did we lose sol 30d"
and returns a structured scope for filtering trades.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Scope:
    window_days: Optional[int] = None   # e.g., 7 -> last 7 days
    last_n_trades: Optional[int] = None # e.g., 20 -> last 20 trades
    symbol: Optional[str] = None        # e.g., "SOL"
    description: str = "recent trades"


WINDOW_PATTERNS = [
    (re.compile(r'(\d+)\s*d'), 'days'),
    (re.compile(r'last\s+(\d+)\s*days'), 'days'),
    (re.compile(r'last\s+(\d+)\s*d'), 'days'),
    (re.compile(r'last\s+(\d+)\s*trades'), 'trades'),
]


def parse_scope(text: str) -> Scope:
    """Parse a scope description from free text."""
    t = text.lower() if text else ""
    window_days = None
    last_n_trades = None
    symbol = None

    # symbol heuristic: "sol", "btc", "eth"
    for sym in ['sol', 'btc', 'eth']:
        if sym in t:
            symbol = sym.upper()
            break

    for pat, kind in WINDOW_PATTERNS:
        m = pat.search(t)
        if m:
            val = int(m.group(1))
            if kind == 'days':
                window_days = val
            elif kind == 'trades':
                last_n_trades = val
            break

    # description
    desc_parts = []
    if symbol:
        desc_parts.append(symbol)
    if window_days:
        desc_parts.append(f"last {window_days}d")
    if last_n_trades:
        desc_parts.append(f"last {last_n_trades} trades")
    description = " / ".join(desc_parts) if desc_parts else "recent trades"

    return Scope(
        window_days=window_days,
        last_n_trades=last_n_trades,
        symbol=symbol,
        description=description,
    )
