# -*- coding: utf-8 -*-
"""
Comprehensive System Context Builder for Telegram Bot AI.

Gathers ALL relevant system data (read-only) for ChatGPT to analyze.
This gives the AI "god mode" visibility into the entire trading system.

Usage:
    from utils.context_builder import SystemContextBuilder

    builder = SystemContextBuilder()
    context = builder.build_full_context()  # For general questions
    diagnostic = builder.run_diagnostic()    # For system review
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Import system components
try:
    import config
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    config = None

try:
    from utils.trade_journal import TradeJournal
    JOURNAL_AVAILABLE = True
except ImportError:
    JOURNAL_AVAILABLE = False

try:
    from utils.system_health import get_health_checker
    HEALTH_AVAILABLE = True
except ImportError:
    HEALTH_AVAILABLE = False

try:
    from filters.filter_manager import FilterManager
    FILTER_AVAILABLE = True
except ImportError:
    FILTER_AVAILABLE = False


class SystemContextBuilder:
    """
    Single source of truth for all system context.

    Provides comprehensive read-only access to:
    - Trade history and performance
    - Filter statistics and rejections
    - System health and errors
    - Configuration values
    - Recent logs
    - Live system state (if running)
    """

    def __init__(self):
        """Initialize context builder with all data sources."""
        self.logs_path = Path("logs")
        self.runs_path = Path("runs")

        # Initialize trade journal
        self.trade_journal = None
        if JOURNAL_AVAILABLE:
            try:
                self.trade_journal = TradeJournal(base_path="runs", enabled=True)
            except Exception as e:
                logger.warning(f"Could not init TradeJournal: {e}")

        # Initialize health checker
        self.health_checker = None
        if HEALTH_AVAILABLE:
            try:
                self.health_checker = get_health_checker()
            except Exception as e:
                logger.warning(f"Could not init HealthChecker: {e}")

        # Path to system documentation
        self.project_root = Path(__file__).parent.parent

        logger.info("✅ SystemContextBuilder initialized")

    # =========================================================================
    # SYSTEM DOCUMENTATION (READ-ONLY)
    # =========================================================================

    def get_system_documentation(self) -> str:
        """
        Read system documentation files for AI context.
        These files explain how the system works and what NOT to change.
        """
        docs = []

        # Read CLAUDE.md (main documentation)
        claude_md = self.project_root / "CLAUDE.md"
        if claude_md.exists():
            try:
                content = claude_md.read_text()
                # Extract key sections only (not the whole file)
                docs.append("=== SYSTEM DOCUMENTATION ===")
                docs.append("Source: CLAUDE.md (READ-ONLY reference)")
                docs.append("")

                # Extract important facts
                docs.append("KEY FACTS:")
                docs.append("• Exchange: Hyperliquid (NOT OKX)")
                docs.append("• Symbol: SOL perpetual futures with 5x leverage")
                docs.append("• Win rate: 36% is INTENTIONAL (3:1 reward-to-risk)")
                docs.append("• Backtest return: +340% over 6 months")
                docs.append("• Adaptive thresholds: DISABLED (better results)")
                docs.append("")
                docs.append("DISABLED FEATURES (do not enable):")
                docs.append("• V4_KELLY_ENABLED - wrong win rate assumptions")
                docs.append("• V4_REGIME_PREDICTION_ENABLED - too conservative")
                docs.append("• V4_PYRAMID_ENABLED - hurt returns")
                docs.append("• ADAPTIVE_THRESHOLD_ENABLED - lost $106 vs fixed")
                docs.append("")
                docs.append("The system is in a LOCKED PERFECT STATE. Do not suggest optimizations.")
            except Exception as e:
                logger.debug(f"Could not read CLAUDE.md: {e}")

        return "\n".join(docs) if docs else ""

    # =========================================================================
    # MAIN CONTEXT BUILDERS
    # =========================================================================

    def build_full_context(self) -> str:
        """
        Build complete context string for ChatGPT.
        Use this for general questions.
        """
        sections = []

        # System documentation first (so AI understands the system)
        sys_docs = self.get_system_documentation()
        if sys_docs:
            sections.append(sys_docs)

        # CRITICAL: Live exchange data (most important)
        exchange_data = self.get_live_position_from_exchange()
        if exchange_data:
            sections.append(self._format_exchange_section(exchange_data))

        # CRITICAL: Real trade history from Hyperliquid (source of truth for P&L)
        hl_history = self.get_hyperliquid_trade_history()
        sections.append(self._format_hyperliquid_history_section(hl_history))

        # Trading summary (local journal - may be incomplete)
        trading = self.get_trading_summary()
        sections.append(self._format_trading_section(trading))

        # Filter summary
        filters = self.get_filter_summary()
        sections.append(self._format_filter_section(filters))

        # System health
        health = self.get_system_health()
        sections.append(self._format_health_section(health))

        # Config summary
        cfg = self.get_config_summary()
        sections.append(self._format_config_section(cfg))

        # Live system state
        live = self._get_live_system_state()
        if live:
            sections.append(self._format_live_section(live))

        return "\n\n".join(sections)

    def explain_feature(self, feature_name: str) -> str:
        """
        Explain why a feature is enabled/disabled.
        Called when user asks about specific settings.
        """
        feature_docs = {
            'adaptive_threshold': (
                "ADAPTIVE_THRESHOLD_ENABLED = False\n\n"
                "WHY DISABLED: Backtest showed +$106 improvement with fixed thresholds.\n"
                "The adaptive system was raising thresholds during drawdowns, missing recovery trades.\n"
                "Fixed threshold of 45 gives consistent results."
            ),
            'kelly': (
                "V4_KELLY_ENABLED = False\n\n"
                "WHY DISABLED: Kelly sizing assumes accurate win rate estimates.\n"
                "Our 36% win rate varies by market regime, causing Kelly to oversize in bad conditions.\n"
                "Fixed 2% risk per trade is more stable."
            ),
            'pyramid': (
                "V4_PYRAMID_ENABLED = False\n\n"
                "WHY DISABLED: Adding to winners increased drawdowns.\n"
                "Backtests showed pyramiding turned profitable trades into losses when reversals hit.\n"
                "Single entry, scaled exits work better."
            ),
            'breakeven': (
                "V4_BREAKEVEN_AFTER_TP1 = False\n\n"
                "WHY DISABLED: Moving stop to breakeven after TP1 caused premature stop-outs.\n"
                "Many winning trades briefly retrace before continuing.\n"
                "Keep original stop loss."
            ),
            'regime_prediction': (
                "V4_REGIME_PREDICTION_ENABLED = False\n\n"
                "WHY DISABLED: Regime predictions were too conservative.\n"
                "System avoided good trades waiting for 'perfect' conditions.\n"
                "Let strategy filters handle market conditions."
            ),
            'win_rate': (
                "WIN RATE: 36%\n\n"
                "This is INTENTIONAL. The system uses a 3:1 reward-to-risk ratio.\n"
                "With 36% wins at 3:1, expected value is positive:\n"
                "  0.36 * 3 - 0.64 * 1 = 1.08 - 0.64 = +0.44 per trade\n"
                "Higher win rate strategies had smaller wins, lower total return.\n"
                "DO NOT try to 'improve' the win rate."
            ),
            'v4_boost': (
                "V4_STRATEGY_BOOST_ENABLED = True\n"
                "V4_BREAKOUT_BOOST = 2.5\n\n"
                "WHY ENABLED: Breakout trades have highest expectancy.\n"
                "2.5x position size on breakouts captured more of winning moves.\n"
                "DO NOT change these values - they're optimized from backtests."
            ),
        }

        # Find matching feature
        feature_lower = feature_name.lower()
        for key, explanation in feature_docs.items():
            if key in feature_lower or feature_lower in key:
                return explanation

        return f"No specific documentation for '{feature_name}'. Check CLAUDE.md for system details."

    def run_diagnostic(self) -> Dict:
        """
        Run full system diagnostic.
        Returns structured data for AI analysis.
        """
        diagnostic = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'trading': self.get_trading_summary(),
            'filters': self.get_filter_summary(),
            'health': self.get_system_health(),
            'config': self.get_config_summary(),
            'recent_errors': self.get_recent_logs(hours=1),
            'issues_found': [],
            'recommendations': [],
        }

        # Analyze and add findings
        self._analyze_diagnostic(diagnostic)

        return diagnostic

    def explain_no_trades(self) -> str:
        """
        Detailed explanation of why system isn't trading.
        Called when user asks "why no trades?"
        """
        # CRITICAL: Check for open position first
        exchange_data = self.get_live_position_from_exchange()
        has_open = exchange_data and exchange_data.get('has_open_position', False)

        trading = self.get_trading_summary()
        filters = self.get_filter_summary()
        health = self.get_system_health()

        explanation = []

        # If there's an open position, the system IS trading!
        if has_open and exchange_data.get('position'):
            pos = exchange_data['position']
            explanation.append("=== SYSTEM IS ACTIVELY TRADING ===")
            explanation.append(f"• OPEN POSITION: {pos['direction']} {pos['size']:.2f} SOL")
            explanation.append(f"• Entry: ${pos['entry_price']:.2f} → Current: ${pos['current_price']:.2f}")
            explanation.append(f"• Unrealized PnL: ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.1f}%)")
            explanation.append("")
            explanation.append("The system has an active trade. It will open new trades after this one closes.")
            return "\n".join(explanation)

        explanation.append("=== WHY NO TRADES ANALYSIS ===")

        # 1. Last trade age
        last_trade_hours = trading.get('last_trade_age_hours', 999)
        if last_trade_hours < 24:
            explanation.append(f"• Last closed trade: {last_trade_hours:.1f} hours ago (normal)")
        else:
            explanation.append(f"• Last closed trade: {last_trade_hours:.1f} hours ago (extended gap)")

        # 2. Signal generation
        total_signals = filters.get('total_checks', 0)
        pass_rate = filters.get('pass_rate', 0)
        explanation.append(f"• Signals checked: {total_signals} in recent period")
        explanation.append(f"• Filter pass rate: {pass_rate*100:.1f}%")

        # 3. Top rejection reasons
        rejections = filters.get('rejections_by_filter', {})
        if rejections:
            explanation.append("• Top rejection reasons:")
            sorted_rejections = sorted(rejections.items(), key=lambda x: x[1], reverse=True)[:5]
            for filter_name, count in sorted_rejections:
                explanation.append(f"  - {filter_name}: {count} rejections")

        # 4. Recent filter decisions
        recent_decisions = self._load_filter_decisions(limit=5)
        if recent_decisions:
            explanation.append("• Recent signal rejections:")
            for decision in recent_decisions[:3]:
                failed = decision.get('failed_filters', [])
                score = decision.get('score', 0)
                explanation.append(f"  - Score {score}/100, failed: {', '.join(failed[:3])}")

        # 5. System health
        errors = health.get('error_count_1h', 0)
        if errors > 0:
            explanation.append(f"• Errors in last hour: {errors}")
        else:
            explanation.append("• System health: No errors")

        # 6. Trading mode
        mode = "LIVE" if not getattr(config, 'OKX_SIMULATED', True) else "PAPER"
        explanation.append(f"• Trading mode: {mode}")

        # 7. Live state
        live = self._get_live_system_state()
        if live:
            if live.get('trading_paused'):
                explanation.append(f"• TRADING PAUSED: {live.get('pause_reason', 'unknown')}")
            else:
                explanation.append(f"• System running: cycle {live.get('cycle_count', 0)}")

        return "\n".join(explanation)

    # =========================================================================
    # DATA GATHERERS
    # =========================================================================

    def get_trading_summary(self) -> Dict:
        """Get trading performance summary."""
        summary = {
            'today_trades': 0,
            'today_wins': 0,
            'today_losses': 0,
            'today_pnl': 0.0,
            'today_win_rate': 0.0,
            'week_trades': 0,
            'week_pnl': 0.0,
            'week_win_rate': 0.0,
            'all_time_trades': 0,
            'all_time_pnl': 0.0,
            'all_time_win_rate': 0.0,
            'best_trade': 0.0,
            'worst_trade': 0.0,
            'current_streak': {'type': 'none', 'count': 0},
            'last_trade_age_hours': 0,  # 0 means no trades yet (not 999)
            'recent_trades': [],
            'open_positions': 0,
            'system_status': 'scanning',  # scanning, trading, paused
            'has_trade_history': False,
        }

        if not self.trade_journal:
            summary['system_status'] = 'scanning - no trade history yet'
            return summary

        try:
            # Get recent trades
            trades = self.trade_journal.get_recent_trades(days=90)

            if not trades:
                summary['system_status'] = 'scanning - waiting for first trade setup'
                return summary

            summary['has_trade_history'] = True
            summary['system_status'] = 'active - has trade history'

            # Calculate last trade age
            if trades:
                last_close = trades[0].get('timestamp_close', '')
                if last_close:
                    try:
                        last_dt = datetime.fromisoformat(last_close.replace('Z', '+00:00'))
                        age = datetime.now(timezone.utc) - last_dt
                        summary['last_trade_age_hours'] = age.total_seconds() / 3600
                    except:
                        pass

            # Recent trades detail (last 10)
            summary['recent_trades'] = [{
                'strategy': t.get('strategy_name', t.get('strategy', 'unknown')),
                'direction': t.get('side', t.get('direction', 'unknown')),
                'pnl': t.get('pnl_abs', t.get('pnl', 0)),
                'pnl_pct': t.get('pnl_pct', 0),
                'close_reason': t.get('close_reason', 'unknown'),
            } for t in trades[:10]]

            # Today's stats
            today = datetime.now(timezone.utc).date()
            today_trades = [t for t in trades if self._get_trade_date(t) == today]
            summary['today_trades'] = len(today_trades)
            summary['today_wins'] = sum(1 for t in today_trades if t.get('pnl_abs', 0) > 0)
            summary['today_losses'] = sum(1 for t in today_trades if t.get('pnl_abs', 0) < 0)
            summary['today_pnl'] = sum(t.get('pnl_abs', 0) for t in today_trades)
            summary['today_win_rate'] = (summary['today_wins'] / summary['today_trades'] * 100) if summary['today_trades'] else 0

            # Week's stats
            week_start = today - timedelta(days=today.weekday())
            week_trades = [t for t in trades if self._get_trade_date(t) and self._get_trade_date(t) >= week_start]
            summary['week_trades'] = len(week_trades)
            summary['week_pnl'] = sum(t.get('pnl_abs', 0) for t in week_trades)
            week_wins = sum(1 for t in week_trades if t.get('pnl_abs', 0) > 0)
            summary['week_win_rate'] = (week_wins / len(week_trades) * 100) if week_trades else 0

            # All-time stats
            summary['all_time_trades'] = len(trades)
            summary['all_time_pnl'] = sum(t.get('pnl_abs', 0) for t in trades)
            all_wins = sum(1 for t in trades if t.get('pnl_abs', 0) > 0)
            summary['all_time_win_rate'] = (all_wins / len(trades) * 100) if trades else 0

            # Best/worst
            pnls = [t.get('pnl_abs', 0) for t in trades]
            summary['best_trade'] = max(pnls) if pnls else 0
            summary['worst_trade'] = min(pnls) if pnls else 0

            # Streak
            summary['current_streak'] = self._calculate_streak(trades)

        except Exception as e:
            logger.error(f"Error getting trading summary: {e}")

        return summary

    def get_filter_summary(self) -> Dict:
        """Get filter statistics and rejection analysis."""
        summary = {
            'total_checks': 0,
            'total_passed': 0,
            'pass_rate': 0.0,
            'rejections_by_filter': {},
            'recent_rejections': [],
            'most_restrictive_filter': 'unknown',
            'score_threshold': 50,
        }

        # Get score threshold from config
        if CONFIG_AVAILABLE:
            summary['score_threshold'] = getattr(config, 'SCORE_THRESHOLD', 50)

        # Try to get filter stats from live system
        live = self._get_live_system_state()
        if live and 'filter_stats' in live:
            stats = live['filter_stats']
            summary['total_checks'] = stats.get('total_checks', 0)
            summary['pass_rate'] = stats.get('pass_rate', 0)
            summary['total_passed'] = int(summary['total_checks'] * summary['pass_rate'])
            summary['rejections_by_filter'] = stats.get('failed_by_filter', {})

            # Find most restrictive
            if summary['rejections_by_filter']:
                most = max(summary['rejections_by_filter'].items(), key=lambda x: x[1])
                summary['most_restrictive_filter'] = most[0]

        # Load recent filter decisions from log
        summary['recent_rejections'] = self._load_filter_decisions(limit=10)

        return summary

    def get_system_health(self) -> Dict:
        """Get system health status."""
        health = {
            'overall_status': 'UNKNOWN',
            'error_count_1h': 0,
            'errors_by_type': {},
            'config_valid': True,
            'config_warnings': [],
            'last_trade_age_hours': 999,
            'api_status': 'unknown',
            'alerts': [],
        }

        # Check for open position - if there's one, system is healthy and active
        exchange_data = self.get_live_position_from_exchange()
        has_open = exchange_data and exchange_data.get('has_open_position', False)

        if self.health_checker:
            try:
                report = self.health_checker.get_health_report()

                # If we have an open position, override health status to HEALTHY
                if has_open:
                    health['overall_status'] = 'HEALTHY - Active Position'
                else:
                    health['overall_status'] = 'HEALTHY' if report.get('is_healthy', False) else 'ISSUES'

                # Filter alerts - remove misleading ones when position is open
                raw_alerts = report.get('alerts', [])
                if has_open:
                    # Remove "no trades" and "critical" alerts when actively trading
                    raw_alerts = [a for a in raw_alerts if 'No trades' not in a and 'stalled' not in a]
                health['alerts'] = raw_alerts

                log_scan = report.get('log_scan', {})
                health['error_count_1h'] = log_scan.get('total_errors', 0)
                health['errors_by_type'] = log_scan.get('errors_by_type', {})

                config_check = report.get('config', {})
                health['config_valid'] = config_check.get('valid', True)
                health['config_warnings'] = config_check.get('warnings', [])

                staleness = report.get('data_staleness', {})
                health['last_trade_age_hours'] = staleness.get('last_trade_age_hours', 999)

            except Exception as e:
                logger.error(f"Error getting health report: {e}")

        return health

    def get_config_summary(self) -> Dict:
        """Get key configuration values."""
        cfg = {
            'trading_mode': 'UNKNOWN',
            'score_threshold': 50,
            'max_risk_per_trade': 0.02,
            'max_daily_trades': 15,
            'leverage': 5,
            'growth_mode': False,
            'v4_enabled': False,
            'v4_strategy_boost': False,
            'v4_breakout_boost': 1.0,
            'strategies_enabled': [],
        }

        if not CONFIG_AVAILABLE:
            return cfg

        try:
            cfg['trading_mode'] = 'PAPER' if getattr(config, 'OKX_SIMULATED', True) else 'LIVE'
            cfg['score_threshold'] = getattr(config, 'SCORE_THRESHOLD', 50)
            cfg['max_risk_per_trade'] = getattr(config, 'MAX_RISK_PER_TRADE', 0.02)
            cfg['max_daily_trades'] = getattr(config, 'MAX_DAILY_TRADES', 15)
            cfg['leverage'] = getattr(config, 'GROWTH_LEVERAGE', 5)
            cfg['growth_mode'] = getattr(config, 'GROWTH_MODE_ENABLED', False)

            # V4 settings
            cfg['v4_enabled'] = getattr(config, 'V4_ENABLED', False)
            cfg['v4_strategy_boost'] = getattr(config, 'V4_STRATEGY_BOOST_ENABLED', False)
            cfg['v4_breakout_boost'] = getattr(config, 'V4_BREAKOUT_BOOST', 1.0)

            # Strategies
            strategies = []
            if getattr(config, 'MEAN_REVERSION_ENABLED', False):
                strategies.append('mean_reversion')
            if getattr(config, 'MOMENTUM_STRATEGY_ENABLED', True):
                strategies.append('momentum')
            strategies.extend(['breakout_v2', 'breakout_v3', 'pullback'])  # Always enabled
            cfg['strategies_enabled'] = strategies

        except Exception as e:
            logger.error(f"Error getting config summary: {e}")

        return cfg

    def get_recent_logs(self, hours: float = 1.0) -> List[str]:
        """Get recent error logs."""
        errors = []

        log_file = self.logs_path / "trading.log"
        if not log_file.exists():
            return errors

        try:
            cutoff = datetime.now() - timedelta(hours=hours)

            # Read last 500 lines efficiently
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-500:]

            for line in lines:
                if 'ERROR' in line or 'CRITICAL' in line or 'Exception' in line:
                    # Skip normal filter rejections
                    if 'FILTER' in line and 'FAILED' in line:
                        continue
                    if 'QUALITY SCORE' in line:
                        continue
                    errors.append(line.strip()[:200])  # Truncate long lines

            return errors[-20:]  # Last 20 errors

        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            return errors

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_live_system_state(self) -> Optional[Dict]:
        """Get live system state if main.py is running."""
        try:
            import sys
            if 'main' in sys.modules:
                main_module = sys.modules['main']
                if hasattr(main_module, 'elite_system') and main_module.elite_system:
                    system = main_module.elite_system
                    return {
                        'is_running': getattr(system, 'running', False),
                        'trading_paused': getattr(system, 'trading_paused', False),
                        'pause_reason': getattr(system, 'pause_reason', ''),
                        'cycle_count': getattr(system, 'cycle_count', 0),
                        'open_positions': len(system.position_tracker.get_open_positions()) if hasattr(system, 'position_tracker') else 0,
                        'filter_stats': system.filter_manager.get_filter_statistics() if hasattr(system, 'filter_manager') else {},
                    }
        except Exception as e:
            logger.debug(f"Could not get live state: {e}")
        return None

    def get_live_position_from_exchange(self) -> Optional[Dict]:
        """Query Hyperliquid directly for live position data."""
        try:
            from data_feed.hyperliquid_client import HyperliquidClient
            client = HyperliquidClient()

            # Get TOTAL EQUITY (not just available/withdrawable balance)
            account_data = client.get_account_balance()
            total_equity = 0.0
            available_balance = 0.0
            if account_data and len(account_data) > 0:
                total_equity = float(account_data[0].get('totalEq', 0))
                details = account_data[0].get('details', [{}])
                if details:
                    available_balance = float(details[0].get('availBal', 0))

            positions = client.get_positions('SOL')
            ticker = client.get_ticker('SOL')

            open_pos = [p for p in positions if abs(float(p.get('pos', 0))) > 0]
            sol_price = float(ticker.get('last', 0)) if ticker else 0

            result = {
                'balance': total_equity,  # NOW SHOWS TOTAL EQUITY!
                'available_balance': available_balance,
                'sol_price': sol_price,
                'has_open_position': len(open_pos) > 0,
                'position': None
            }

            if open_pos:
                p = open_pos[0]
                pos_size = float(p.get('pos', 0))
                entry = float(p.get('avgPx', 0))
                upl = float(p.get('upl', 0))
                direction = 'SHORT' if pos_size < 0 else 'LONG'

                result['position'] = {
                    'direction': direction,
                    'size': abs(pos_size),
                    'entry_price': entry,
                    'current_price': sol_price,
                    'unrealized_pnl': upl,
                    'pnl_pct': ((entry - sol_price) / entry * 100) if pos_size < 0 else ((sol_price - entry) / entry * 100)
                }

            return result
        except Exception as e:
            logger.error(f"Error getting live position from exchange: {e}")
            return None

    def get_hyperliquid_trade_history(self) -> Dict:
        """
        Fetch REAL trade history directly from Hyperliquid API.
        This is the source of truth for P&L - not the local trade journal.

        Returns fills with closedPnl for accurate profit/loss tracking.
        """
        try:
            import requests
            import os
            from dotenv import load_dotenv
            load_dotenv()

            address = os.getenv('HYPERLIQUID_WALLET_ADDRESS', '')
            if not address:
                logger.warning("No HYPERLIQUID_WALLET_ADDRESS set")
                return {'fills': [], 'total_realized_pnl': 0, 'error': 'No wallet address'}

            # Fetch fills from Hyperliquid
            response = requests.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'userFills', 'user': address},
                timeout=10
            )

            if response.status_code != 200:
                logger.error(f"Hyperliquid API error: {response.status_code}")
                return {'fills': [], 'total_realized_pnl': 0, 'error': f'API error {response.status_code}'}

            fills = response.json()

            # Parse fills into structured format
            parsed_fills = []
            total_realized_pnl = 0.0

            for fill in fills:
                closed_pnl = float(fill.get('closedPnl', 0))
                total_realized_pnl += closed_pnl

                ts = int(fill.get('time', 0))
                time_str = datetime.fromtimestamp(ts/1000).strftime('%Y-%m-%d %H:%M') if ts else 'N/A'

                parsed_fills.append({
                    'timestamp': time_str,
                    'timestamp_ms': ts,
                    'side': 'BUY' if fill.get('side') == 'B' else 'SELL',
                    'size': float(fill.get('sz', 0)),
                    'price': float(fill.get('px', 0)),
                    'closed_pnl': closed_pnl,
                    'coin': fill.get('coin', 'SOL'),
                })

            # Sort by timestamp (newest first)
            parsed_fills.sort(key=lambda x: x['timestamp_ms'], reverse=True)

            # Group fills into complete trades (entry + exit = 1 trade)
            # A trade closes when closedPnl != 0
            completed_trades = []
            for fill in parsed_fills:
                if fill['closed_pnl'] != 0:
                    completed_trades.append({
                        'timestamp': fill['timestamp'],
                        'side': fill['side'],
                        'size': fill['size'],
                        'exit_price': fill['price'],
                        'pnl': fill['closed_pnl'],
                        'result': 'WIN' if fill['closed_pnl'] > 0 else 'LOSS'
                    })

            return {
                'fills': parsed_fills[:20],  # Last 20 fills
                'completed_trades': completed_trades[:10],  # Last 10 closed trades
                'total_realized_pnl': total_realized_pnl,
                'total_fills': len(fills),
                'total_completed_trades': len(completed_trades),
                'wins': sum(1 for t in completed_trades if t['pnl'] > 0),
                'losses': sum(1 for t in completed_trades if t['pnl'] < 0),
            }

        except Exception as e:
            logger.error(f"Error fetching Hyperliquid trade history: {e}")
            return {'fills': [], 'total_realized_pnl': 0, 'error': str(e)}

    def _load_filter_decisions(self, limit: int = 10) -> List[Dict]:
        """Load recent filter decisions from JSONL log."""
        decisions = []
        log_file = self.logs_path / "filter_decisions.jsonl"

        if not log_file.exists():
            return decisions

        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()[-limit*2:]  # Read extra in case of parsing errors

            for line in reversed(lines):
                if line.strip():
                    try:
                        decision = json.loads(line)
                        decisions.append({
                            'timestamp': decision.get('timestamp', ''),
                            'score': decision.get('score', 0),
                            'passed': decision.get('passed', False),
                            'failed_filters': decision.get('failed_filters', []),
                            'strategy': decision.get('strategy', 'unknown'),
                        })
                        if len(decisions) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Error loading filter decisions: {e}")

        return decisions

    def _get_trade_date(self, trade: Dict):
        """Extract date from trade."""
        ts = trade.get('timestamp_close', trade.get('_logged_at', ''))
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.date()
            except:
                pass
        return None

    def _calculate_streak(self, trades: List[Dict]) -> Dict:
        """Calculate current win/loss streak."""
        if not trades:
            return {'type': 'none', 'count': 0}

        first_is_win = trades[0].get('pnl_abs', 0) > 0
        streak_type = 'win' if first_is_win else 'loss'
        count = 0

        for trade in trades:
            is_win = trade.get('pnl_abs', 0) > 0
            if (streak_type == 'win' and is_win) or (streak_type == 'loss' and not is_win):
                count += 1
            else:
                break

        return {'type': streak_type, 'count': count}

    def _analyze_diagnostic(self, diagnostic: Dict):
        """Analyze diagnostic data and add findings."""
        issues = []
        recommendations = []

        trading = diagnostic['trading']
        filters = diagnostic['filters']
        health = diagnostic['health']

        # CRITICAL: Check for open position first - if there's one, system is active
        exchange_data = self.get_live_position_from_exchange()
        has_open_position = exchange_data and exchange_data.get('has_open_position', False)

        # Check for no trading (only if no open position)
        last_trade_hours = trading.get('last_trade_age_hours', 999)
        if has_open_position:
            # Active position - don't report "no trades" issue
            pass
        elif last_trade_hours > 48:
            issues.append(f"No closed trades in {last_trade_hours:.0f} hours")
            recommendations.append("Check filter thresholds - may be too strict")
        elif last_trade_hours > 24:
            issues.append(f"Last closed trade was {last_trade_hours:.0f} hours ago")

        # Check filter pass rate
        pass_rate = filters.get('pass_rate', 0)
        if pass_rate < 0.01 and filters.get('total_checks', 0) > 10:
            issues.append(f"Very low filter pass rate: {pass_rate*100:.1f}%")
            most_restrictive = filters.get('most_restrictive_filter', 'unknown')
            recommendations.append(f"Review {most_restrictive} filter thresholds")

        # Check for errors
        error_count = health.get('error_count_1h', 0)
        if error_count > 10:
            issues.append(f"High error rate: {error_count} errors in last hour")
            recommendations.append("Check logs for API or connection issues")

        # Check config
        if not health.get('config_valid', True):
            issues.append("Configuration validation failed")
            recommendations.extend(health.get('config_warnings', []))

        # Check win rate trend
        if trading.get('all_time_trades', 0) > 20:
            win_rate = trading.get('all_time_win_rate', 0)
            if win_rate < 35:
                issues.append(f"Low win rate: {win_rate:.1f}%")
                recommendations.append("Review strategy performance by type")

        diagnostic['issues_found'] = issues
        diagnostic['recommendations'] = recommendations

    # =========================================================================
    # FORMATTERS
    # =========================================================================

    def _format_trading_section(self, data: Dict) -> str:
        """Format trading summary for context."""
        lines = ["=== TRADING PERFORMANCE ==="]

        # Check for open position first - this is critical context
        exchange_data = self.get_live_position_from_exchange()
        has_open = exchange_data and exchange_data.get('has_open_position', False)

        if has_open and exchange_data.get('position'):
            pos = exchange_data['position']
            lines.append(f"*** ACTIVE TRADE: {pos['direction']} {pos['size']:.2f} SOL ***")
            lines.append(f"   Entry: ${pos['entry_price']:.2f} → Current: ${pos['current_price']:.2f}")
            lines.append(f"   Unrealized PnL: ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.1f}%)")
            lines.append("")

        # Show system status
        status = data.get('system_status', 'unknown')
        if has_open:
            status = "ACTIVE - Position open"
        lines.append(f"System Status: {status}")

        if not data.get('has_trade_history', False) and not has_open:
            lines.append("NOTE: System is NEW - no completed trades yet. This is normal.")
            lines.append("The system scans every minute and trades when conditions are perfect.")
            return "\n".join(lines)

        lines.append(f"Today (closed): {data['today_trades']} trades ({data['today_wins']}W/{data['today_losses']}L) PnL: ${data['today_pnl']:+.2f}")
        lines.append(f"Week: {data['week_trades']} trades PnL: ${data['week_pnl']:+.2f} WR: {data['week_win_rate']:.0f}%")
        lines.append(f"All-time: {data['all_time_trades']} trades PnL: ${data['all_time_pnl']:+.2f} WR: {data['all_time_win_rate']:.0f}%")
        lines.append(f"Best: ${data['best_trade']:+.2f} | Worst: ${data['worst_trade']:+.2f}")
        lines.append(f"Streak: {data['current_streak']['count']} {data['current_streak']['type']}s")

        last_hours = data['last_trade_age_hours']
        if has_open:
            lines.append(f"Last closed trade: {last_hours:.1f}h ago (current trade still open)")
        elif last_hours > 0:
            lines.append(f"Last closed trade: {last_hours:.1f} hours ago")
        else:
            lines.append("Last trade: No completed trades yet")

        if data['recent_trades']:
            lines.append("Recent closed trades:")
            for t in data['recent_trades'][:5]:
                lines.append(f"  • {t['strategy']} {t['direction'].upper()} ${t['pnl']:+.2f} ({t['close_reason']})")

        return "\n".join(lines)

    def _format_exchange_section(self, data: Dict) -> str:
        """Format live exchange data for context."""
        lines = ["=== LIVE EXCHANGE DATA (HYPERLIQUID) ==="]
        lines.append(f"Account Balance: ${data['balance']:.2f} USDT")
        lines.append(f"SOL Price: ${data['sol_price']:.2f}")

        if data['has_open_position'] and data['position']:
            pos = data['position']
            lines.append("")
            lines.append("*** OPEN POSITION ***")
            lines.append(f"Direction: {pos['direction']}")
            lines.append(f"Size: {pos['size']:.2f} SOL")
            lines.append(f"Entry: ${pos['entry_price']:.2f}")
            lines.append(f"Current: ${pos['current_price']:.2f}")
            lines.append(f"Unrealized PnL: ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:.2f}%)")
        else:
            lines.append("Open Position: None")

        return "\n".join(lines)

    def _format_hyperliquid_history_section(self, data: Dict) -> str:
        """Format real Hyperliquid trade history for context."""
        lines = ["=== REAL TRADE HISTORY (HYPERLIQUID - SOURCE OF TRUTH) ==="]

        if data.get('error'):
            lines.append(f"Error fetching data: {data['error']}")
            return "\n".join(lines)

        total_pnl = data.get('total_realized_pnl', 0)
        total_trades = data.get('total_completed_trades', 0)
        wins = data.get('wins', 0)
        losses = data.get('losses', 0)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        lines.append(f"Total Realized P&L: ${total_pnl:+.4f}")
        lines.append(f"Completed Trades: {total_trades} ({wins}W / {losses}L) - {win_rate:.0f}% win rate")
        lines.append("")

        # Show recent completed trades (these are the REAL results)
        completed = data.get('completed_trades', [])
        if completed:
            lines.append("Recent Closed Trades (VERIFIED FROM EXCHANGE):")
            for trade in completed[:5]:
                result_emoji = "✅" if trade['pnl'] > 0 else "❌"
                lines.append(f"  {result_emoji} {trade['timestamp']} | {trade['side']} {trade['size']:.2f} SOL @ ${trade['exit_price']:.2f} | P&L: ${trade['pnl']:+.4f}")
        else:
            lines.append("No completed trades yet")

        lines.append("")
        lines.append("NOTE: This data comes directly from Hyperliquid API - it's the true P&L.")

        return "\n".join(lines)

    def _format_filter_section(self, data: Dict) -> str:
        """Format filter summary for context."""
        lines = ["=== FILTER STATISTICS ==="]
        lines.append(f"Total checks: {data['total_checks']} | Passed: {data['total_passed']} | Rate: {data['pass_rate']*100:.1f}%")
        lines.append(f"Score threshold: {data['score_threshold']}")
        lines.append(f"Most restrictive: {data['most_restrictive_filter']}")

        if data['rejections_by_filter']:
            lines.append("Rejections by filter:")
            sorted_rej = sorted(data['rejections_by_filter'].items(), key=lambda x: x[1], reverse=True)[:5]
            for name, count in sorted_rej:
                lines.append(f"  • {name}: {count}")

        return "\n".join(lines)

    def _format_health_section(self, data: Dict) -> str:
        """Format health summary for context."""
        lines = ["=== SYSTEM HEALTH ==="]
        lines.append(f"Status: {data['overall_status']}")
        lines.append(f"Errors (1h): {data['error_count_1h']}")
        lines.append(f"Config valid: {'Yes' if data['config_valid'] else 'No'}")

        # Filter out misleading alerts
        alerts = data.get('alerts', [])
        # Remove "no trades" and "stalled" alerts - these are misleading when position is open
        filtered_alerts = [a for a in alerts if 'No trades in' not in a and 'stalled' not in a]
        # Also filter out CRITICAL errors that are just filter rejections (normal behavior)
        filtered_alerts = [a for a in filtered_alerts if 'CRITICAL errors' not in a or data['error_count_1h'] > 5]

        if filtered_alerts:
            lines.append(f"Alerts: {', '.join(filtered_alerts[:3])}")
        else:
            lines.append("Alerts: None - System healthy")

        return "\n".join(lines)

    def _format_config_section(self, data: Dict) -> str:
        """Format config summary for context."""
        lines = ["=== CONFIGURATION ==="]
        lines.append(f"Mode: {data['trading_mode']}")
        lines.append(f"Score threshold: {data['score_threshold']}")
        lines.append(f"Risk per trade: {data['max_risk_per_trade']*100:.1f}%")
        lines.append(f"Leverage: {data['leverage']}x")
        lines.append(f"V4 enabled: {data['v4_enabled']} | Strategy boost: {data['v4_strategy_boost']} ({data['v4_breakout_boost']}x)")
        lines.append(f"Strategies: {', '.join(data['strategies_enabled'])}")

        return "\n".join(lines)

    def _format_live_section(self, data: Dict) -> str:
        """Format live system state for context."""
        lines = ["=== LIVE SYSTEM STATE ==="]
        lines.append(f"Running: {data['is_running']}")
        lines.append(f"Trading paused: {data['trading_paused']}")
        if data['trading_paused']:
            lines.append(f"Pause reason: {data['pause_reason']}")
        lines.append(f"Cycle count: {data['cycle_count']}")
        lines.append(f"Open positions: {data['open_positions']}")

        return "\n".join(lines)


# Singleton instance
_context_builder = None

def get_context_builder() -> SystemContextBuilder:
    """Get singleton context builder instance."""
    global _context_builder
    if _context_builder is None:
        _context_builder = SystemContextBuilder()
    return _context_builder
