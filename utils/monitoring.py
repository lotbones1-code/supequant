# -*- coding: utf-8 -*-
"""
Elite Monitoring System - READ ONLY

Tracks system metrics without affecting trading logic:
- V4 multiplier logging per trade
- Balance/equity tracking over time
- Proactive error detection
- Daily performance summaries

THIS FILE IS MONITORING ONLY - NO TRADING LOGIC
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import threading

logger = logging.getLogger(__name__)


@dataclass
class TradeLog:
    """Detailed trade log with V4 info"""
    timestamp: str
    trade_id: str
    symbol: str
    direction: str
    strategy: str
    score: float
    entry_price: float
    position_size: float
    notional_value: float

    # V4 details
    v4_enabled: bool = False
    v4_multiplier: float = 1.0
    strategy_boost: float = 1.0
    score_mult: float = 1.0

    # Account state
    account_balance: float = 0.0
    margin_used: float = 0.0
    leverage: int = 5

    # Outcome (filled later)
    exit_price: Optional[float] = None
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    close_reason: Optional[str] = None


@dataclass
class BalanceSnapshot:
    """Point-in-time balance record"""
    timestamp: str
    total_balance: float
    available_balance: float
    unrealized_pnl: float
    margin_used: float
    open_positions: int
    daily_pnl: float
    cumulative_pnl: float


class MonitoringSystem:
    """
    Comprehensive monitoring without affecting trading.

    Features:
    - Detailed V4 trade logging
    - Balance tracking for equity curve
    - Error rate monitoring
    - Proactive alerts
    """

    def __init__(self, data_dir: str = "data/monitoring"):
        """Initialize monitoring system."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.trade_log_path = self.data_dir / "detailed_trades.jsonl"
        self.balance_log_path = self.data_dir / "balance_history.jsonl"
        self.daily_summary_path = self.data_dir / "daily_summaries.json"
        self.error_log_path = self.data_dir / "error_tracking.jsonl"

        # In-memory state
        self._today_trades: List[TradeLog] = []
        self._today_errors: List[Dict] = []
        self._last_balance: Optional[float] = None
        self._starting_balance: Optional[float] = None
        self._lock = threading.Lock()

        # Load today's data
        self._load_today_data()

        logger.info("📊 MonitoringSystem initialized (read-only tracking)")

    def _load_today_data(self):
        """Load today's trades from log."""
        today = datetime.now(timezone.utc).date().isoformat()

        if self.trade_log_path.exists():
            try:
                with open(self.trade_log_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('timestamp', '').startswith(today):
                                self._today_trades.append(TradeLog(**data))
            except Exception as e:
                logger.warning(f"Could not load today's trades: {e}")

    # =========================================================================
    # TRADE LOGGING
    # =========================================================================

    def log_trade_entry(self, signal: Dict, position_details: Dict,
                        account_balance: float) -> str:
        """
        Log detailed trade entry with V4 multipliers.

        Call this when a trade is opened.
        Returns trade_id for later matching.
        """
        trade_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{signal.get('strategy', 'unknown')[:3]}"

        v4_details = position_details.get('v4_details', {})

        trade = TradeLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            trade_id=trade_id,
            symbol=signal.get('symbol', 'SOL-USDT-SWAP'),
            direction=signal.get('direction', signal.get('side', 'unknown')),
            strategy=signal.get('strategy', signal.get('strategy_name', 'unknown')),
            score=signal.get('score', signal.get('quality_score', 0)),
            entry_price=signal.get('entry_price', 0),
            position_size=position_details.get('position_size', 0),
            notional_value=position_details.get('notional_value', 0),
            v4_enabled=position_details.get('v4_multiplier', 1.0) != 1.0,
            v4_multiplier=position_details.get('v4_multiplier', 1.0),
            strategy_boost=v4_details.get('strategy_boost', 1.0),
            score_mult=v4_details.get('score_mult', 1.0),
            account_balance=account_balance,
            margin_used=position_details.get('notional_value', 0) / position_details.get('leverage', 5),
            leverage=position_details.get('leverage', 5),
        )

        with self._lock:
            self._today_trades.append(trade)
            self._append_jsonl(self.trade_log_path, asdict(trade))

        logger.info(f"📝 Trade logged: {trade_id} | V4 mult: {trade.v4_multiplier:.2f}x | "
                   f"Strategy: {trade.strategy_boost}x | Score: {trade.score_mult}x")

        return trade_id

    def log_trade_exit(self, trade_id: str, exit_price: float,
                       pnl_usd: float, pnl_pct: float, close_reason: str):
        """
        Update trade log with exit details.

        Call this when a trade is closed.
        """
        with self._lock:
            # Find and update trade
            for trade in self._today_trades:
                if trade.trade_id == trade_id:
                    trade.exit_price = exit_price
                    trade.pnl_usd = pnl_usd
                    trade.pnl_pct = pnl_pct
                    trade.close_reason = close_reason

                    # Append updated record
                    self._append_jsonl(self.trade_log_path, asdict(trade))

                    logger.info(f"📝 Trade exit logged: {trade_id} | PnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)")
                    return

        # If not found in today's trades, just log the exit
        exit_record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'trade_id': trade_id,
            'exit_price': exit_price,
            'pnl_usd': pnl_usd,
            'pnl_pct': pnl_pct,
            'close_reason': close_reason,
            'type': 'exit_only'
        }
        self._append_jsonl(self.trade_log_path, exit_record)

    # =========================================================================
    # BALANCE TRACKING
    # =========================================================================

    def log_balance(self, total_balance: float, available_balance: float,
                    unrealized_pnl: float = 0, margin_used: float = 0,
                    open_positions: int = 0):
        """
        Log balance snapshot for equity curve tracking.

        Call this periodically (e.g., every hour or after trades).
        """
        if self._starting_balance is None:
            self._starting_balance = total_balance

        daily_pnl = total_balance - (self._last_balance or total_balance)
        cumulative_pnl = total_balance - self._starting_balance

        snapshot = BalanceSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_balance=total_balance,
            available_balance=available_balance,
            unrealized_pnl=unrealized_pnl,
            margin_used=margin_used,
            open_positions=open_positions,
            daily_pnl=daily_pnl,
            cumulative_pnl=cumulative_pnl,
        )

        self._last_balance = total_balance
        self._append_jsonl(self.balance_log_path, asdict(snapshot))

        logger.debug(f"💰 Balance logged: ${total_balance:.2f} | Daily: ${daily_pnl:+.2f}")

    def get_equity_curve(self, days: int = 30) -> List[Dict]:
        """Get balance history for equity curve."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        snapshots = []

        if self.balance_log_path.exists():
            try:
                with open(self.balance_log_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('timestamp', '') >= cutoff:
                                snapshots.append(data)
            except Exception as e:
                logger.error(f"Error reading balance history: {e}")

        return snapshots

    # =========================================================================
    # ERROR TRACKING
    # =========================================================================

    def log_error(self, error_type: str, message: str, details: Dict = None):
        """
        Log an error for monitoring.

        Call this when errors occur (API failures, order rejections, etc.)
        """
        error_record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'type': error_type,
            'message': message[:500],  # Truncate long messages
            'details': details or {},
        }

        with self._lock:
            self._today_errors.append(error_record)
            self._append_jsonl(self.error_log_path, error_record)

        logger.warning(f"⚠️ Error logged: {error_type} - {message[:100]}")

    def get_error_rate(self, hours: float = 1.0) -> Dict:
        """Get error statistics for the last N hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        errors = []
        if self.error_log_path.exists():
            try:
                with open(self.error_log_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('timestamp', '') >= cutoff:
                                errors.append(data)
            except Exception as e:
                logger.error(f"Error reading error log: {e}")

        # Count by type
        by_type = {}
        for err in errors:
            err_type = err.get('type', 'unknown')
            by_type[err_type] = by_type.get(err_type, 0) + 1

        return {
            'total_errors': len(errors),
            'by_type': by_type,
            'hours': hours,
        }

    # =========================================================================
    # DAILY SUMMARIES
    # =========================================================================

    def generate_daily_summary(self) -> Dict:
        """
        Generate comprehensive daily summary.

        Returns dict suitable for Telegram message.
        """
        today = datetime.now(timezone.utc).date().isoformat()

        # Get today's trades
        today_trades = [t for t in self._today_trades if t.timestamp.startswith(today)]
        completed_trades = [t for t in today_trades if t.pnl_usd is not None]

        # Calculate stats
        total_pnl = sum(t.pnl_usd or 0 for t in completed_trades)
        wins = [t for t in completed_trades if (t.pnl_usd or 0) > 0]
        losses = [t for t in completed_trades if (t.pnl_usd or 0) < 0]

        # V4 analysis
        v4_trades = [t for t in completed_trades if t.v4_enabled]
        v4_pnl = sum(t.pnl_usd or 0 for t in v4_trades)

        # Strategy breakdown
        by_strategy = {}
        for t in completed_trades:
            strat = t.strategy
            if strat not in by_strategy:
                by_strategy[strat] = {'trades': 0, 'pnl': 0, 'wins': 0}
            by_strategy[strat]['trades'] += 1
            by_strategy[strat]['pnl'] += t.pnl_usd or 0
            if (t.pnl_usd or 0) > 0:
                by_strategy[strat]['wins'] += 1

        # Get balance info
        equity = self.get_equity_curve(days=1)
        start_balance = equity[0]['total_balance'] if equity else 0
        end_balance = equity[-1]['total_balance'] if equity else 0

        # Error stats
        errors = self.get_error_rate(hours=24)

        summary = {
            'date': today,
            'generated_at': datetime.now(timezone.utc).isoformat(),

            # Trade stats
            'total_trades': len(completed_trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': (len(wins) / len(completed_trades) * 100) if completed_trades else 0,
            'total_pnl': total_pnl,
            'best_trade': max((t.pnl_usd or 0) for t in completed_trades) if completed_trades else 0,
            'worst_trade': min((t.pnl_usd or 0) for t in completed_trades) if completed_trades else 0,

            # V4 stats
            'v4_trades': len(v4_trades),
            'v4_pnl': v4_pnl,
            'v4_pct_of_trades': (len(v4_trades) / len(completed_trades) * 100) if completed_trades else 0,

            # Strategy breakdown
            'by_strategy': by_strategy,

            # Balance
            'start_balance': start_balance,
            'end_balance': end_balance,
            'balance_change': end_balance - start_balance,
            'balance_change_pct': ((end_balance / start_balance - 1) * 100) if start_balance else 0,

            # Errors
            'errors_24h': errors['total_errors'],
            'errors_by_type': errors['by_type'],
        }

        # Save summary
        self._save_daily_summary(summary)

        return summary

    def _save_daily_summary(self, summary: Dict):
        """Save daily summary to file."""
        try:
            # Load existing summaries
            summaries = {}
            if self.daily_summary_path.exists():
                with open(self.daily_summary_path, 'r') as f:
                    summaries = json.load(f)

            # Add/update today's
            summaries[summary['date']] = summary

            # Keep last 90 days
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
            summaries = {k: v for k, v in summaries.items() if k >= cutoff}

            with open(self.daily_summary_path, 'w') as f:
                json.dump(summaries, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving daily summary: {e}")

    def format_daily_summary_telegram(self, summary: Dict = None) -> str:
        """Format daily summary for Telegram message."""
        if summary is None:
            summary = self.generate_daily_summary()

        lines = []
        lines.append(f"📊 <b>Daily Summary - {summary['date']}</b>")
        lines.append("")

        # Trade stats
        lines.append(f"📈 <b>Trades:</b> {summary['total_trades']}")
        lines.append(f"   ✅ Wins: {summary['wins']} | ❌ Losses: {summary['losses']}")
        lines.append(f"   Win Rate: {summary['win_rate']:.1f}%")
        lines.append(f"   PnL: <b>${summary['total_pnl']:+.2f}</b>")

        if summary['total_trades'] > 0:
            lines.append(f"   Best: ${summary['best_trade']:+.2f} | Worst: ${summary['worst_trade']:+.2f}")

        # V4 stats
        if summary['v4_trades'] > 0:
            lines.append("")
            lines.append(f"🚀 <b>V4 Boosted Trades:</b> {summary['v4_trades']} ({summary['v4_pct_of_trades']:.0f}%)")
            lines.append(f"   V4 PnL: ${summary['v4_pnl']:+.2f}")

        # Strategy breakdown
        if summary['by_strategy']:
            lines.append("")
            lines.append("📋 <b>By Strategy:</b>")
            for strat, data in summary['by_strategy'].items():
                wr = (data['wins'] / data['trades'] * 100) if data['trades'] else 0
                lines.append(f"   • {strat}: {data['trades']} trades, ${data['pnl']:+.2f} ({wr:.0f}% WR)")

        # Balance
        lines.append("")
        lines.append(f"💰 <b>Balance:</b> ${summary['end_balance']:.2f}")
        lines.append(f"   Change: ${summary['balance_change']:+.2f} ({summary['balance_change_pct']:+.1f}%)")

        # Errors
        if summary['errors_24h'] > 0:
            lines.append("")
            lines.append(f"⚠️ <b>Errors (24h):</b> {summary['errors_24h']}")
            for err_type, count in summary['errors_by_type'].items():
                lines.append(f"   • {err_type}: {count}")

        return "\n".join(lines)

    # =========================================================================
    # PROACTIVE ALERTS
    # =========================================================================

    def check_alerts(self) -> List[str]:
        """
        Check for conditions that should trigger proactive alerts.

        Returns list of alert messages.
        """
        alerts = []

        # Check error rate
        errors = self.get_error_rate(hours=1)
        if errors['total_errors'] > 10:
            alerts.append(f"⚠️ High error rate: {errors['total_errors']} errors in last hour")

        # Check for specific error types
        if errors['by_type'].get('api_error', 0) > 5:
            alerts.append("🔴 API errors detected - check OKX connection")
        if errors['by_type'].get('order_rejected', 0) > 3:
            alerts.append("🔴 Multiple order rejections - check account status")

        # Check trading activity
        today = datetime.now(timezone.utc).date().isoformat()
        today_trades = [t for t in self._today_trades if t.timestamp.startswith(today)]

        hours_since_trade = 999
        if today_trades:
            last_trade_time = max(t.timestamp for t in today_trades)
            last_dt = datetime.fromisoformat(last_trade_time.replace('Z', '+00:00'))
            hours_since_trade = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600

        # Alert if no trades for a while (during market hours)
        if hours_since_trade > 24:
            alerts.append(f"ℹ️ No trades in {hours_since_trade:.0f} hours - market may be quiet")

        return alerts

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _append_jsonl(self, path: Path, data: Dict):
        """Append a record to a JSONL file."""
        try:
            with open(path, 'a') as f:
                f.write(json.dumps(data) + '\n')
        except Exception as e:
            logger.error(f"Error writing to {path}: {e}")

    def get_v4_performance(self, days: int = 30) -> Dict:
        """Get V4 vs non-V4 performance comparison."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        v4_trades = []
        non_v4_trades = []

        if self.trade_log_path.exists():
            try:
                with open(self.trade_log_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('timestamp', '') >= cutoff and data.get('pnl_usd') is not None:
                                if data.get('v4_enabled'):
                                    v4_trades.append(data)
                                else:
                                    non_v4_trades.append(data)
            except Exception as e:
                logger.error(f"Error reading trade log: {e}")

        def calc_stats(trades):
            if not trades:
                return {'trades': 0, 'pnl': 0, 'win_rate': 0, 'avg_pnl': 0}
            wins = sum(1 for t in trades if t['pnl_usd'] > 0)
            total_pnl = sum(t['pnl_usd'] for t in trades)
            return {
                'trades': len(trades),
                'pnl': total_pnl,
                'win_rate': wins / len(trades) * 100,
                'avg_pnl': total_pnl / len(trades),
            }

        return {
            'v4': calc_stats(v4_trades),
            'non_v4': calc_stats(non_v4_trades),
            'days': days,
        }


# Singleton instance
_monitoring_system = None

def get_monitoring_system() -> MonitoringSystem:
    """Get singleton monitoring system instance."""
    global _monitoring_system
    if _monitoring_system is None:
        _monitoring_system = MonitoringSystem()
    return _monitoring_system
