# -*- coding: utf-8 -*-
"""
Analytics responder for Telegram bot.

Given a list of trades and an optional scope, produces:
- Summary (always sent)
- Details (optional follow-up)

All numbers are derived from provided trades only (no guesses).
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from collections import Counter


@dataclass
class AnalysisResult:
    summary: str
    details: Optional[str] = None


def _filter_trades(trades: List[Dict], scope) -> List[Dict]:
    """Apply scope filters to trades (window_days, last_n_trades, symbol)."""
    filtered = trades
    # symbol filter
    if scope and scope.symbol:
        filtered = [t for t in filtered if scope.symbol in t.get('symbol', '').upper()]
    # last_n_trades
    if scope and scope.last_n_trades:
        filtered = filtered[:scope.last_n_trades]
    return filtered


def _summarize(trades: List[Dict]) -> Dict:
    total = len(trades)
    wins = sum(1 for t in trades if t.get('pnl_abs', t.get('pnl', 0)) > 0)
    losses = total - wins
    pnl = sum(t.get('pnl_abs', t.get('pnl', 0)) for t in trades)
    win_rate = (wins / total * 100) if total else 0
    return {
        'total': total,
        'wins': wins,
        'losses': losses,
        'pnl': pnl,
        'win_rate': win_rate,
    }


def _top_drivers(trades: List[Dict], key: str, top_n: int = 3) -> List[Tuple[str, float]]:
    counter: Counter = Counter()
    for t in trades:
        name = t.get(key, 'unknown') or 'unknown'
        pnl = t.get('pnl_abs', t.get('pnl', 0))
        counter[name] += pnl
    return counter.most_common(top_n)


def analyze_trades(trades: List[Dict], scope=None) -> AnalysisResult:
    """
    Analyze trades and return summary + optional details.
    Trades are assumed sorted newest→oldest.
    """
    scoped = _filter_trades(trades, scope)
    stats = _summarize(scoped)
    desc = scope.description if scope else "recent trades"

    if stats['total'] == 0:
        return AnalysisResult(summary=f"📭 No trades to analyze ({desc}).")

    summary = (
        f"📊 ANALYSIS ({desc})\n"
        f"• Trades: {stats['total']} ({stats['wins']}W/{stats['losses']}L)\n"
        f"• Win rate: {stats['win_rate']:.1f}%\n"
        f"• PnL: ${stats['pnl']:+.2f}"
    )

    # Drivers by strategy and close reason
    top_strats = _top_drivers(scoped, 'strategy', top_n=3)
    top_reasons = _top_drivers(scoped, 'close_reason', top_n=3)

    def fmt_drivers(drivers):
        return "\n".join([f"  • {name}: ${pnl:+.2f}" for name, pnl in drivers if name != 'unknown'])

    details_lines = []
    if top_strats:
        details_lines.append("Strategies:")
        details_lines.append(fmt_drivers(top_strats))
    if top_reasons:
        details_lines.append("Close reasons:")
        details_lines.append(fmt_drivers(top_reasons))

    details = "\n".join(details_lines) if details_lines else None
    return AnalysisResult(summary=summary, details=details)
