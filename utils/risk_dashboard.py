"""
Risk Exposure Dashboard - Phase 1.5 Module 3

Real-time risk exposure analytics dashboard.
READ-ONLY - Does not affect trading decisions.

Provides:
- Current position risk exposure
- Drawdown tracking
- Value at Risk (VaR) estimates
- Kelly Criterion recommendations
- Session statistics

Usage:
    from utils.risk_dashboard import RiskDashboard
    
    dashboard = RiskDashboard(risk_manager, production_manager)
    print(dashboard.generate_report())
"""

import os
import sys
import json
import glob
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Try to import numpy for VaR calculations
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("numpy not available - VaR calculations disabled")


class RiskDashboard:
    """
    Real-time risk exposure analytics dashboard.
    
    This is READ-ONLY analytics - it does NOT affect trading decisions.
    All calculations are informational for monitoring purposes.
    """
    
    # Minimum trades required for statistical calculations
    MIN_TRADES_VAR = 10
    MIN_TRADES_KELLY = 20
    
    def __init__(self, risk_manager=None, production_manager=None, 
                 trade_journal_path: str = 'runs'):
        """
        Initialize the risk dashboard.
        
        Args:
            risk_manager: RiskManager instance (optional)
            production_manager: ProductionOrderManager instance (optional)
            trade_journal_path: Path to trade journal files
        """
        self.risk_manager = risk_manager
        self.production_manager = production_manager
        self.trade_journal_path = trade_journal_path
        
        # Drawdown tracking
        self.peak_equity = None
        self.equity_history: List[Tuple[datetime, float]] = []
        self.max_historical_drawdown_pct = 0.0
        
        # Cache
        self._trades_cache = None
        self._trades_cache_time = None
        self._cache_ttl = 60  # seconds
        
        logger.info("📊 RiskDashboard initialized (read-only analytics)")
    
    def _load_trades(self, days: int = 30) -> List[Dict]:
        """
        Load trades from TradeJournal JSONL files.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of trade dictionaries
        """
        # Check cache
        now = datetime.now()
        if (self._trades_cache is not None and 
            self._trades_cache_time and 
            (now - self._trades_cache_time).total_seconds() < self._cache_ttl):
            return self._trades_cache
        
        trades = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Find all trades.jsonl files
        pattern = os.path.join(self.trade_journal_path, "**/trades.jsonl")
        trade_files = glob.glob(pattern, recursive=True)
        
        for filepath in trade_files:
            try:
                # Extract date from path (runs/YYYY-MM-DD/trades.jsonl)
                dir_name = os.path.basename(os.path.dirname(filepath))
                try:
                    file_date = datetime.strptime(dir_name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if file_date < cutoff_date:
                        continue
                except ValueError:
                    pass  # Not a date-formatted directory
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                trade = json.loads(line)
                                trades.append(trade)
                            except json.JSONDecodeError:
                                pass
                                
            except Exception as e:
                logger.debug(f"Error reading {filepath}: {e}")
        
        # Update cache
        self._trades_cache = trades
        self._trades_cache_time = now
        
        return trades
    
    def _get_account_balance(self) -> float:
        """Get current account balance from risk manager."""
        if self.risk_manager:
            try:
                balance = self.risk_manager.get_account_balance()
                if balance:
                    return balance
            except Exception as e:
                logger.debug(f"Could not get balance from risk_manager: {e}")
        return 0.0
    
    def _get_current_position(self) -> Optional[Any]:
        """Get current position from production manager."""
        if self.production_manager:
            try:
                return self.production_manager.current_position
            except Exception as e:
                logger.debug(f"Could not get position: {e}")
        return None
    
    def _get_current_price(self, symbol: str = 'SOL-USDT') -> float:
        """Get current price for symbol."""
        if self.production_manager and self.production_manager.client:
            try:
                ticker = self.production_manager.client.get_ticker(symbol)
                if ticker and 'data' in ticker and ticker['data']:
                    return float(ticker['data'][0].get('last', 0))
            except Exception:
                pass
        return 0.0
    
    def get_current_exposure(self) -> Dict[str, Any]:
        """
        Get current position risk exposure.
        
        Returns:
            Dict with position details and risk metrics
        """
        position = self._get_current_position()
        account_balance = self._get_account_balance()
        
        # No position case
        if not position or not hasattr(position, 'state'):
            return {
                'has_position': False,
                'status': 'NO_POSITION',
                'status_icon': '⚪',
                'message': 'No open position',
                'account_balance': account_balance
            }
        
        # Check if position is active
        try:
            from execution.production_manager import PositionState
            if position.state != PositionState.ACTIVE:
                return {
                    'has_position': False,
                    'status': 'NO_POSITION',
                    'status_icon': '⚪',
                    'message': f'Position state: {position.state.value}',
                    'account_balance': account_balance
                }
        except ImportError:
            pass
        
        # Get current price
        current_price = self._get_current_price(position.symbol)
        if current_price == 0:
            current_price = position.entry_price  # Fallback
        
        # Calculate position value
        position_size = position.actual_entry_size or position.entry_size or 0
        position_value_usd = position_size * current_price
        
        # Calculate unrealized PnL
        if position.direction == 'long':
            unrealized_pnl = (current_price - position.entry_price) * position_size
            unrealized_pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
        else:
            unrealized_pnl = (position.entry_price - current_price) * position_size
            unrealized_pnl_pct = ((position.entry_price - current_price) / position.entry_price) * 100
        
        # Calculate risk to stop loss
        risk_dollars = abs(position.entry_price - position.stop_loss) * position_size
        risk_percent = (risk_dollars / account_balance * 100) if account_balance > 0 else 0
        
        # Determine status
        if risk_percent < 2:
            status = 'SAFE'
            status_icon = '✅'
        elif risk_percent < 3:
            status = 'WATCH'
            status_icon = '🟡'
        else:
            status = 'ALERT'
            status_icon = '❌'
        
        return {
            'has_position': True,
            'symbol': position.symbol,
            'direction': position.direction,
            'entry_price': position.entry_price,
            'current_price': current_price,
            'stop_loss': position.stop_loss,
            'tp1_price': position.tp1_price,
            'tp2_price': position.tp2_price,
            'position_size': position_size,
            'position_value_usd': round(position_value_usd, 2),
            'unrealized_pnl': round(unrealized_pnl, 2),
            'unrealized_pnl_pct': round(unrealized_pnl_pct, 2),
            'risk_dollars': round(risk_dollars, 2),
            'risk_percent': round(risk_percent, 2),
            'account_balance': round(account_balance, 2),
            'status': status,
            'status_icon': status_icon
        }
    
    def get_drawdown(self) -> Dict[str, Any]:
        """
        Calculate current drawdown from peak equity.
        
        Returns:
            Dict with drawdown metrics
        """
        current_equity = self._get_account_balance()
        now = datetime.now(timezone.utc)
        
        # Handle zero/missing equity
        if current_equity <= 0:
            return {
                'has_data': False,
                'status': 'NO_DATA',
                'status_icon': '⚪',
                'message': 'Unable to get account balance'
            }
        
        # Initialize or update peak
        if self.peak_equity is None or current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        # Record equity history (keep last 100)
        self.equity_history.append((now, current_equity))
        if len(self.equity_history) > 100:
            self.equity_history = self.equity_history[-100:]
        
        # Calculate current drawdown
        current_drawdown_dollars = current_equity - self.peak_equity
        current_drawdown_pct = ((current_equity - self.peak_equity) / self.peak_equity) * 100
        
        # Calculate max historical drawdown from equity history
        if len(self.equity_history) >= 2:
            equities = [e[1] for e in self.equity_history]
            running_peak = equities[0]
            max_dd = 0
            for eq in equities:
                if eq > running_peak:
                    running_peak = eq
                dd = ((eq - running_peak) / running_peak) * 100
                if dd < max_dd:
                    max_dd = dd
            self.max_historical_drawdown_pct = max_dd
        
        # Determine status
        dd_abs = abs(current_drawdown_pct)
        if dd_abs < 5:
            status = 'OK'
            status_icon = '✅'
        elif dd_abs < 10:
            status = 'WATCH'
            status_icon = '🟡'
        else:
            status = 'ALERT'
            status_icon = '❌'
        
        return {
            'has_data': True,
            'current_equity': round(current_equity, 2),
            'peak_equity': round(self.peak_equity, 2),
            'current_drawdown_dollars': round(current_drawdown_dollars, 2),
            'current_drawdown_pct': round(current_drawdown_pct, 2),
            'max_historical_drawdown_pct': round(self.max_historical_drawdown_pct, 2),
            'equity_history_points': len(self.equity_history),
            'status': status,
            'status_icon': status_icon
        }
    
    def calculate_var(self, confidence_level: float = 0.95) -> Dict[str, Any]:
        """
        Calculate Value at Risk from historical trade returns.
        
        Args:
            confidence_level: Confidence level (default 0.95 = 95%)
            
        Returns:
            Dict with VaR metrics
        """
        if not NUMPY_AVAILABLE:
            return {
                'has_sufficient_data': False,
                'status': 'UNAVAILABLE',
                'status_icon': '⚪',
                'message': 'numpy not installed - VaR unavailable'
            }
        
        trades = self._load_trades(days=30)
        account_balance = self._get_account_balance()
        
        # Check minimum trades
        if len(trades) < self.MIN_TRADES_VAR:
            return {
                'has_sufficient_data': False,
                'trades_analyzed': len(trades),
                'trades_required': self.MIN_TRADES_VAR,
                'status': 'INSUFFICIENT_DATA',
                'status_icon': '⚪',
                'message': f'Need {self.MIN_TRADES_VAR - len(trades)} more trades for VaR'
            }
        
        # Extract returns (pnl_pct)
        returns = []
        for trade in trades:
            pnl_pct = trade.get('pnl_pct')
            if pnl_pct is not None:
                returns.append(pnl_pct)
        
        if len(returns) < self.MIN_TRADES_VAR:
            return {
                'has_sufficient_data': False,
                'trades_analyzed': len(returns),
                'trades_required': self.MIN_TRADES_VAR,
                'status': 'INSUFFICIENT_DATA',
                'status_icon': '⚪',
                'message': f'Need {self.MIN_TRADES_VAR - len(returns)} more trades with PnL data'
            }
        
        # Calculate VaR using percentile method
        percentile = (1 - confidence_level) * 100  # 5th percentile for 95% confidence
        var_pct = np.percentile(returns, percentile)
        var_dollars = (var_pct / 100) * account_balance if account_balance > 0 else 0
        
        # Additional statistics
        avg_return = np.mean(returns)
        worst_return = np.min(returns)
        best_return = np.max(returns)
        
        # Determine status
        if var_pct > -3:
            status = 'ACCEPTABLE'
            status_icon = '✅'
        elif var_pct > -5:
            status = 'MONITOR'
            status_icon = '🟡'
        else:
            status = 'ALERT'
            status_icon = '❌'
        
        return {
            'has_sufficient_data': True,
            'trades_analyzed': len(returns),
            'confidence_level': confidence_level,
            'var_per_trade_pct': round(var_pct, 2),
            'var_per_trade_dollars': round(var_dollars, 2),
            'avg_trade_return_pct': round(avg_return, 2),
            'worst_trade_pct': round(worst_return, 2),
            'best_trade_pct': round(best_return, 2),
            'status': status,
            'status_icon': status_icon
        }
    
    def get_kelly_recommendation(self) -> Dict[str, Any]:
        """
        Calculate Kelly Criterion optimal position sizing.
        
        Returns:
            Dict with Kelly recommendations
        """
        trades = self._load_trades(days=30)
        
        # Check minimum trades
        if len(trades) < self.MIN_TRADES_KELLY:
            return {
                'has_sufficient_data': False,
                'trades_analyzed': len(trades),
                'trades_required': self.MIN_TRADES_KELLY,
                'status': 'INSUFFICIENT_DATA',
                'status_icon': '⚪',
                'message': f'Need {self.MIN_TRADES_KELLY - len(trades)} more trades for Kelly'
            }
        
        # Separate wins and losses
        wins = []
        losses = []
        for trade in trades:
            pnl_pct = trade.get('pnl_pct')
            if pnl_pct is None:
                continue
            if pnl_pct > 0:
                wins.append(pnl_pct)
            elif pnl_pct < 0:
                losses.append(abs(pnl_pct))
        
        total_trades = len(wins) + len(losses)
        
        if total_trades < self.MIN_TRADES_KELLY:
            return {
                'has_sufficient_data': False,
                'trades_analyzed': total_trades,
                'trades_required': self.MIN_TRADES_KELLY,
                'status': 'INSUFFICIENT_DATA',
                'status_icon': '⚪',
                'message': f'Need {self.MIN_TRADES_KELLY - total_trades} more trades with PnL'
            }
        
        # Handle edge cases
        if len(wins) == 0:
            return {
                'has_sufficient_data': True,
                'trades_analyzed': total_trades,
                'wins': 0,
                'losses': len(losses),
                'win_rate': 0,
                'status': 'WARNING',
                'status_icon': '❌',
                'message': 'No winning trades - Kelly suggests no risk',
                'kelly_full_pct': 0,
                'kelly_half_pct': 0,
                'kelly_quarter_pct': 0
            }
        
        if len(losses) == 0:
            return {
                'has_sufficient_data': True,
                'trades_analyzed': total_trades,
                'wins': len(wins),
                'losses': 0,
                'win_rate': 1.0,
                'status': 'CAUTION',
                'status_icon': '🟡',
                'message': 'No losing trades yet - Kelly unreliable',
                'avg_win_pct': round(sum(wins) / len(wins), 2),
                'kelly_full_pct': None,
                'kelly_half_pct': None,
                'kelly_quarter_pct': None
            }
        
        # Calculate Kelly
        win_rate = len(wins) / total_trades
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        # Kelly formula: (b*p - q) / b
        # where b = win/loss ratio, p = win probability, q = 1-p
        b = win_loss_ratio
        p = win_rate
        q = 1 - p
        
        if b > 0:
            kelly_full = ((b * p) - q) / b
        else:
            kelly_full = 0
        
        # Clamp to reasonable range (0% to 25%)
        kelly_full = max(0, min(kelly_full * 100, 25))
        kelly_half = kelly_full * 0.5
        kelly_quarter = kelly_full * 0.25
        
        # Determine status
        if kelly_full > 5:
            status = 'OPTIMAL'
            status_icon = '✅'
        elif kelly_full > 2:
            status = 'MODERATE'
            status_icon = '🟡'
        elif kelly_full > 0:
            status = 'CONSERVATIVE'
            status_icon = '🟡'
        else:
            status = 'NO_EDGE'
            status_icon = '❌'
        
        return {
            'has_sufficient_data': True,
            'trades_analyzed': total_trades,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(win_rate, 3),
            'win_rate_pct': round(win_rate * 100, 1),
            'avg_win_pct': round(avg_win, 2),
            'avg_loss_pct': round(avg_loss, 2),
            'win_loss_ratio': round(win_loss_ratio, 2),
            'kelly_full_pct': round(kelly_full, 2),
            'kelly_half_pct': round(kelly_half, 2),
            'kelly_quarter_pct': round(kelly_quarter, 2),
            'recommended_risk_pct': round(kelly_quarter, 2),  # Conservative recommendation
            'status': status,
            'status_icon': status_icon
        }
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get today's trading session statistics.
        
        Returns:
            Dict with session metrics
        """
        trades = self._load_trades(days=1)
        
        # Filter to today only
        today = datetime.now(timezone.utc).date()
        today_trades = []
        for trade in trades:
            try:
                close_time = trade.get('timestamp_close')
                if close_time:
                    trade_date = datetime.fromisoformat(close_time.replace('Z', '+00:00')).date()
                    if trade_date == today:
                        today_trades.append(trade)
            except Exception:
                pass
        
        if not today_trades:
            return {
                'has_trades': False,
                'trades_today': 0,
                'message': 'No trades today'
            }
        
        wins = [t for t in today_trades if t.get('pnl_abs', 0) > 0]
        losses = [t for t in today_trades if t.get('pnl_abs', 0) <= 0]
        
        total_pnl = sum(t.get('pnl_abs', 0) for t in today_trades)
        
        # Calculate average duration
        durations = [t.get('duration_seconds', 0) for t in today_trades if t.get('duration_seconds')]
        avg_duration_min = (sum(durations) / len(durations) / 60) if durations else 0
        
        # Best and worst trades
        pnls = [t.get('pnl_abs', 0) for t in today_trades]
        best_pnl = max(pnls) if pnls else 0
        worst_pnl = min(pnls) if pnls else 0
        
        return {
            'has_trades': True,
            'trades_today': len(today_trades),
            'wins_today': len(wins),
            'losses_today': len(losses),
            'win_rate_today': round(len(wins) / len(today_trades) * 100, 1) if today_trades else 0,
            'pnl_today_dollars': round(total_pnl, 2),
            'best_trade_pnl': round(best_pnl, 2),
            'worst_trade_pnl': round(worst_pnl, 2),
            'avg_trade_duration_minutes': round(avg_duration_min, 1)
        }
    
    def generate_report(self) -> str:
        """
        Generate formatted risk dashboard report.
        
        Returns:
            Beautifully formatted report string
        """
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        
        exposure = self.get_current_exposure()
        drawdown = self.get_drawdown()
        var = self.calculate_var()
        kelly = self.get_kelly_recommendation()
        session = self.get_session_stats()
        
        def pad(content: str) -> str:
            return f"║ {content.ljust(58)} ║"
        
        lines = []
        lines.append("╔════════════════════════════════════════════════════════════╗")
        lines.append("║              RISK EXPOSURE DASHBOARD                       ║")
        lines.append(pad(f"Time: {now}"))
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Current Position Section
        lines.append(pad("CURRENT POSITION"))
        if exposure.get('has_position'):
            lines.append(pad(f"  Status: {exposure['status_icon']} {exposure['status']}"))
            lines.append(pad(f"  Direction: {exposure['direction'].upper()} {exposure['symbol']}"))
            lines.append(pad(f"  Size: {exposure['position_size']:.4f} (${exposure['position_value_usd']:.2f})"))
            lines.append(pad(f"  Entry: ${exposure['entry_price']:.2f} | Current: ${exposure['current_price']:.2f}"))
            pnl_sign = '+' if exposure['unrealized_pnl'] >= 0 else ''
            lines.append(pad(f"  Unrealized PnL: {pnl_sign}${exposure['unrealized_pnl']:.2f} ({pnl_sign}{exposure['unrealized_pnl_pct']:.2f}%)"))
            lines.append(pad(f"  Risk to SL: ${exposure['risk_dollars']:.2f} ({exposure['risk_percent']:.1f}% of capital)"))
        else:
            lines.append(pad(f"  {exposure['status_icon']} {exposure.get('message', 'No open position')}"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Drawdown Section
        lines.append(pad("DRAWDOWN"))
        if drawdown.get('has_data'):
            lines.append(pad(f"  Status: {drawdown['status_icon']} {drawdown['status']}"))
            dd_sign = '+' if drawdown['current_drawdown_pct'] >= 0 else ''
            lines.append(pad(f"  Current: {dd_sign}{drawdown['current_drawdown_pct']:.1f}% (${drawdown['current_drawdown_dollars']:.2f})"))
            lines.append(pad(f"  Peak Equity: ${drawdown['peak_equity']:.2f}"))
            lines.append(pad(f"  Max Historical: {drawdown['max_historical_drawdown_pct']:.1f}%"))
        else:
            lines.append(pad(f"  {drawdown['status_icon']} {drawdown.get('message', 'No data')}"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # VaR Section
        lines.append(pad("VALUE AT RISK (95% Confidence)"))
        if var.get('has_sufficient_data'):
            lines.append(pad(f"  Status: {var['status_icon']} {var['status']}"))
            lines.append(pad(f"  VaR per Trade: {var['var_per_trade_pct']:.2f}% (${var['var_per_trade_dollars']:.2f})"))
            lines.append(pad(f"  Avg Return: {var['avg_trade_return_pct']:.2f}%"))
            lines.append(pad(f"  Range: {var['worst_trade_pct']:.2f}% to +{var['best_trade_pct']:.2f}%"))
            lines.append(pad(f"  Based on: {var['trades_analyzed']} trades"))
        else:
            lines.append(pad(f"  {var['status_icon']} {var.get('message', 'Insufficient data')}"))
            if var.get('trades_analyzed') is not None:
                lines.append(pad(f"  Progress: {var['trades_analyzed']}/{var.get('trades_required', self.MIN_TRADES_VAR)} trades"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Kelly Section
        lines.append(pad("KELLY CRITERION"))
        if kelly.get('has_sufficient_data') and kelly.get('kelly_full_pct') is not None:
            lines.append(pad(f"  Status: {kelly['status_icon']} {kelly['status']}"))
            lines.append(pad(f"  Win Rate: {kelly['win_rate_pct']:.1f}% ({kelly['wins']}W/{kelly['losses']}L)"))
            lines.append(pad(f"  Win/Loss Ratio: {kelly['win_loss_ratio']:.2f}x"))
            lines.append(pad(f"  Full Kelly: {kelly['kelly_full_pct']:.1f}%"))
            lines.append(pad(f"  Recommended (1/4 Kelly): {kelly['kelly_quarter_pct']:.2f}%"))
        else:
            lines.append(pad(f"  {kelly['status_icon']} {kelly.get('message', 'Insufficient data')}"))
            if kelly.get('trades_analyzed') is not None:
                lines.append(pad(f"  Progress: {kelly['trades_analyzed']}/{kelly.get('trades_required', self.MIN_TRADES_KELLY)} trades"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Session Stats
        lines.append(pad("TODAY'S SESSION"))
        if session.get('has_trades'):
            lines.append(pad(f"  Trades: {session['trades_today']} | Wins: {session['wins_today']} | Losses: {session['losses_today']}"))
            pnl_sign = '+' if session['pnl_today_dollars'] >= 0 else ''
            lines.append(pad(f"  PnL: {pnl_sign}${session['pnl_today_dollars']:.2f}"))
            lines.append(pad(f"  Avg Duration: {session['avg_trade_duration_minutes']:.1f} minutes"))
        else:
            lines.append(pad("  No trades today"))
        
        lines.append("╚════════════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary dict for API/dashboard use.
        
        Returns:
            Dict with all metrics
        """
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'exposure': self.get_current_exposure(),
            'drawdown': self.get_drawdown(),
            'var': self.calculate_var(),
            'kelly': self.get_kelly_recommendation(),
            'session': self.get_session_stats()
        }


# Module-level singleton helper
_dashboard_instance = None

def get_risk_dashboard(risk_manager=None, production_manager=None) -> RiskDashboard:
    """Get or create the global RiskDashboard instance."""
    global _dashboard_instance
    if _dashboard_instance is None:
        _dashboard_instance = RiskDashboard(risk_manager, production_manager)
    return _dashboard_instance


# CLI for testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    print("\n📊 Risk Exposure Dashboard Test\n")
    
    # Create dashboard without managers (will show limited data)
    dashboard = RiskDashboard()
    
    # Print report
    print(dashboard.generate_report())
    
    # Print summary
    print("\n📋 Summary Dict:")
    summary = dashboard.get_summary()
    print(f"   Exposure status: {summary['exposure'].get('status', 'N/A')}")
    print(f"   Drawdown status: {summary['drawdown'].get('status', 'N/A')}")
    print(f"   VaR status: {summary['var'].get('status', 'N/A')}")
    print(f"   Kelly status: {summary['kelly'].get('status', 'N/A')}")
    
    print("\n✅ Risk Dashboard test complete!")
