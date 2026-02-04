"""
System Health Utilities - Proactive Health Monitoring

Provides:
- Log scanning for errors
- Config validation
- Data staleness detection
- Health summary for Telegram bot

Usage:
    from utils.system_health import SystemHealthChecker, get_health_checker

    checker = get_health_checker()
    report = checker.get_health_report()
    telegram_msg = checker.generate_telegram_summary()
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class SystemHealthChecker:
    """
    Proactive system health monitoring.

    Scans logs, validates config, detects stale data,
    and provides comprehensive health reports.
    """

    def __init__(self, logs_path: str = "logs", runs_path: str = "runs"):
        """
        Initialize health checker.

        Args:
            logs_path: Path to log files
            runs_path: Path to trade journal data
        """
        self.logs_path = Path(logs_path)
        self.runs_path = Path(runs_path)

        # Error patterns to scan for (pattern, error_type)
        # Note: CRITICAL pattern is checked AFTER exclusions, so normal filter rejections are skipped
        self.error_patterns = [
            (r'ERROR.*API', 'api_error'),
            (r'ERROR.*timeout', 'timeout'),
            (r'ERROR.*connection', 'connection'),
            (r'CRITICAL(?!.*FILTER)(?!.*filters:)', 'critical'),  # CRITICAL but NOT filter-related
            (r'Exception.*Traceback', 'exception'),
            (r'51155', 'compliance_error'),  # OKX compliance
            (r'rate limit', 'rate_limit'),
            (r'❌.*failed', 'failed_operation'),
            (r'Could not', 'operation_failed'),
        ]
        
        # Exclusion patterns - these are normal operations, not errors
        # Filter rejections are GOOD - they mean the system is working correctly
        self.exclude_patterns = [
            r'CRITICAL FILTER FAILED',        # Normal filter rejections - this is a feature name, not error level
            r'CRITICAL.*FILTER.*FAILED',      # Normal filter rejections (with or without emoji)
            r'❌.*CRITICAL.*FILTER.*FAILED',  # Normal filter rejections with emoji
            r'❌.*FILTER.*FAILED',            # Normal filter rejections
            r'❌.*TRADE REJECTED',            # Normal trade rejections
            r'❌.*QUALITY SCORE',             # Normal quality score rejections
            r'QUALITY SCORE TOO LOW',         # Normal quality score rejections
            r'filter_manager.*CRITICAL',       # Any CRITICAL from filter_manager (normal operations)
            r'\[INFO\].*filter_manager',       # ALL [INFO] level from filter_manager are normal (actual log format)
            r'\[INFO\].*CRITICAL FILTER',      # INFO level CRITICAL FILTER messages (normal rejections)
            r'filter_manager:\d+.*CRITICAL',   # filter_manager with line number + CRITICAL (normal)
            r'filter_manager:99',             # Line 99 is initialization (not an error)
            r'filters\.filter_manager:99',    # Line 99 with full module path (not an error)
            r'[Cc]ritical filters?',          # Initialization log - "Critical filter" or "Critical filters" (case-insensitive)
            r'Critical filters \(binary\)',   # Initialization log (not an error)
        ]

        logger.debug("SystemHealthChecker initialized")

    def scan_logs_for_errors(self, hours: float = 1.0) -> Dict[str, Any]:
        """
        Scan recent log files for errors.

        Args:
            hours: How many hours back to scan

        Returns:
            Dict with error counts and samples
        """
        results = {
            'errors_found': 0,
            'by_type': {},
            'recent_samples': [],
            'scan_period_hours': hours,
            'files_scanned': 0
        }

        if not self.logs_path.exists():
            results['warning'] = 'Logs directory not found'
            return results

        cutoff = datetime.now() - timedelta(hours=hours)

        # Find log files modified recently
        log_files = list(self.logs_path.glob('*.log'))
        results['files_scanned'] = len(log_files)

        for log_file in log_files:
            try:
                # Check modification time
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    continue

                # Scan file
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    # Read last 1000 lines to avoid memory issues
                    lines = f.readlines()[-1000:]

                    for line in lines:
                        # FIRST: Exclude filter_manager INFO messages that are normal operations
                        # These are initialization logs and filter rejections (not errors)
                        # Log format: "2026-01-28 19:14:45 [INFO] filters.filter_manager:152 - ❌ CRITICAL FILTER FAILED"
                        if 'filter_manager' in line and '[INFO]' in line:
                            # ALL INFO-level filter_manager messages are normal operations
                            continue  # Skip - these are trade rejections which are GOOD

                        # Also skip any "CRITICAL FILTER FAILED" - this is a feature name, not error level
                        if 'CRITICAL FILTER FAILED' in line:
                            continue  # Skip - this is normal filter rejection messaging
                        
                        # SECOND: Check exclusion patterns (normal operations)
                        is_excluded = any(re.search(exclude_pattern, line, re.IGNORECASE) 
                                         for exclude_pattern in self.exclude_patterns)
                        if is_excluded:
                            continue  # Skip normal filter rejections - these are not errors
                        
                        for pattern, error_type in self.error_patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                results['errors_found'] += 1
                                results['by_type'][error_type] = results['by_type'].get(error_type, 0) + 1

                                # Keep sample (max 10)
                                if len(results['recent_samples']) < 10:
                                    # Extract timestamp if present
                                    timestamp = ''
                                    ts_match = re.match(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
                                    if ts_match:
                                        timestamp = ts_match.group(1)

                                    results['recent_samples'].append({
                                        'type': error_type,
                                        'file': log_file.name,
                                        'timestamp': timestamp,
                                        'message': line.strip()[:200]
                                    })
                                break  # Only count each line once

            except Exception as e:
                logger.warning(f"Error scanning {log_file}: {e}")

        return results

    def validate_config(self) -> Dict[str, Any]:
        """
        Validate critical configuration settings.

        Returns:
            Dict with validation results
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'checks_passed': 0,
            'checks_failed': 0
        }

        try:
            import config

            # Check 1: Perpetual-only (CRITICAL)
            # Hyperliquid uses bare coin names ("SOL"), OKX used "SOL-USDT-SWAP"
            # Validate via TRADING_MODE instead of symbol suffix
            if config.TRADING_MODE != 'perp':
                results['errors'].append('TRADING_MODE must be "perp" for perpetual trading')
                results['checks_failed'] += 1
            else:
                results['checks_passed'] += 1

            # Check 2: Trading mode
            if config.TRADING_MODE != 'perp':
                results['errors'].append('TRADING_MODE must be "perp"')
                results['checks_failed'] += 1
            else:
                results['checks_passed'] += 1

            # Check 3: Spot fallback disabled
            if getattr(config, 'SPOT_FALLBACK_ENABLED', True):
                results['errors'].append('SPOT_FALLBACK_ENABLED must be False')
                results['checks_failed'] += 1
            else:
                results['checks_passed'] += 1

            # Check 4: Risk limits (warnings only)
            max_risk = getattr(config, 'MAX_RISK_PER_TRADE', 0.02)
            if max_risk > 0.05:
                results['warnings'].append(f'MAX_RISK_PER_TRADE is high: {max_risk*100:.0f}%')
            else:
                results['checks_passed'] += 1

            # Check 5: Daily loss limit
            max_daily_loss = getattr(config, 'MAX_DAILY_LOSS_PCT', 0.05)
            if max_daily_loss > 0.10:
                results['warnings'].append(f'MAX_DAILY_LOSS_PCT is high: {max_daily_loss*100:.0f}%')
            else:
                results['checks_passed'] += 1

            # Check 6: API credentials (warn if missing)
            hl_key = getattr(config, 'HYPERLIQUID_PRIVATE_KEY', '')
            hl_addr = getattr(config, 'HYPERLIQUID_WALLET_ADDRESS', '')
            if not hl_key or not hl_addr:
                results['warnings'].append('Hyperliquid API credentials missing')
            else:
                results['checks_passed'] += 1

            results['valid'] = len(results['errors']) == 0

        except ImportError as e:
            results['valid'] = False
            results['errors'].append(f'Could not import config: {e}')

        return results

    def check_data_staleness(self) -> Dict[str, Any]:
        """
        Check if trade data is stale (no recent activity).

        Returns:
            Dict with staleness info
        """
        results = {
            'is_stale': False,
            'last_trade_age_hours': None,
            'last_trade_date': None,
            'trades_today': 0,
            'trades_this_week': 0,
            'has_open_position': False
        }

        # CRITICAL: Check for open positions on exchange first
        # If there's an open position, the system is NOT stale
        try:
            from data_feed.hyperliquid_client import HyperliquidClient
            client = HyperliquidClient()
            positions = client.get_positions('SOL')
            open_pos = [p for p in positions if abs(float(p.get('pos', 0))) > 0]
            if open_pos:
                results['has_open_position'] = True
                results['is_stale'] = False  # Never stale if position is open
        except Exception as e:
            logger.debug(f"Could not check exchange positions: {e}")

        if not self.runs_path.exists():
            results['warning'] = 'Runs directory not found'
            return results

        # Find most recent trades.jsonl
        trade_files = sorted(self.runs_path.glob('*/trades.jsonl'), reverse=True)

        if not trade_files:
            results['is_stale'] = True
            results['warning'] = 'No trade history found'
            return results

        # Get most recent trade
        most_recent_trade = None
        for trade_file in trade_files[:7]:  # Check last 7 days
            try:
                with open(trade_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            trade = json.loads(line)
                            ts = trade.get('timestamp_close', trade.get('_logged_at'))
                            if ts and (most_recent_trade is None or ts > most_recent_trade):
                                most_recent_trade = ts
            except Exception:
                pass

        if most_recent_trade:
            try:
                # Handle timezone-aware parsing
                if most_recent_trade.endswith('Z'):
                    most_recent_trade = most_recent_trade.replace('Z', '+00:00')
                trade_dt = datetime.fromisoformat(most_recent_trade)

                # Make timezone aware if needed
                if trade_dt.tzinfo is None:
                    trade_dt = trade_dt.replace(tzinfo=timezone.utc)

                age = datetime.now(timezone.utc) - trade_dt
                results['last_trade_age_hours'] = round(age.total_seconds() / 3600, 1)
                results['last_trade_date'] = most_recent_trade[:10]

                # Consider stale if no trades in 48+ hours AND no open position
                # If there's an open position, the system is active (not stale)
                if not results.get('has_open_position'):
                    results['is_stale'] = age.total_seconds() > 48 * 3600
            except Exception as e:
                logger.debug(f"Error parsing trade timestamp: {e}")

        # Count today's trades
        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        today_file = self.runs_path / today_str / 'trades.jsonl'
        if today_file.exists():
            try:
                with open(today_file, 'r') as f:
                    results['trades_today'] = sum(1 for line in f if line.strip())
            except Exception:
                pass

        # Count this week's trades
        week_trades = 0
        for i in range(7):
            day = datetime.now(timezone.utc) - timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            day_file = self.runs_path / day_str / 'trades.jsonl'
            if day_file.exists():
                try:
                    with open(day_file, 'r') as f:
                        week_trades += sum(1 for line in f if line.strip())
                except Exception:
                    pass
        results['trades_this_week'] = week_trades

        return results

    def get_health_report(self) -> Dict[str, Any]:
        """
        Get comprehensive health report.

        Returns:
            Dict with all health metrics
        """
        log_scan = self.scan_logs_for_errors(hours=1.0)
        config_check = self.validate_config()
        staleness = self.check_data_staleness()

        # Determine overall health
        is_healthy = True
        alerts = []

        if not config_check['valid']:
            is_healthy = False
            alerts.extend(config_check['errors'])

        if log_scan['errors_found'] > 10:
            is_healthy = False
            alerts.append(f"High error rate: {log_scan['errors_found']} errors in last hour")

        if staleness.get('is_stale') and not staleness.get('has_open_position'):
            alerts.append("No trades in 48+ hours - system may be stalled")
        elif staleness.get('has_open_position'):
            # Active position - this is good, not an alert
            pass

        # Check for critical errors
        critical_count = log_scan['by_type'].get('critical', 0)
        if critical_count > 0:
            is_healthy = False
            alerts.append(f"CRITICAL errors detected: {critical_count}")

        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'is_healthy': is_healthy,
            'alerts': alerts,
            'log_scan': log_scan,
            'config': config_check,
            'data_staleness': staleness
        }

    def generate_telegram_summary(self) -> str:
        """
        Generate Telegram-formatted health summary.

        Returns:
            HTML-formatted string for Telegram
        """
        report = self.get_health_report()

        # Status icon
        if report['is_healthy']:
            status = "HEALTHY"
        else:
            status = "ISSUES DETECTED"

        lines = [f"<b>SYSTEM HEALTH</b>\n{status}\n"]

        # Config
        config = report['config']
        config_status = "passed" if config['valid'] else "FAILED"
        lines.append(f"<b>Config:</b> {config['checks_passed']} checks {config_status}")
        if config['errors']:
            for err in config['errors'][:2]:
                lines.append(f"   {err}")

        # Errors
        errors = report['log_scan']
        lines.append(f"\n<b>Errors (1h):</b> {errors['errors_found']}")
        if errors['by_type']:
            types = ', '.join(f"{k}:{v}" for k, v in list(errors['by_type'].items())[:3])
            lines.append(f"   Types: {types}")

        # Data
        staleness = report['data_staleness']

        # Show open position status prominently
        if staleness.get('has_open_position'):
            lines.append("\n<b>ACTIVE POSITION:</b> Yes (trade in progress)")

        if staleness.get('last_trade_age_hours') is not None:
            lines.append(f"<b>Last Closed Trade:</b> {staleness['last_trade_age_hours']:.1f}h ago")
        lines.append(f"<b>Trades Today:</b> {staleness.get('trades_today', 0)}")
        lines.append(f"<b>Trades This Week:</b> {staleness.get('trades_this_week', 0)}")

        # Alerts
        if report['alerts']:
            lines.append("\n<b>Alerts:</b>")
            for alert in report['alerts'][:3]:
                lines.append(f"   {alert}")

        return '\n'.join(lines)

    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent errors for display.

        Args:
            limit: Maximum number of errors to return

        Returns:
            List of error dicts with timestamp, type, message
        """
        scan = self.scan_logs_for_errors(hours=24.0)
        return scan.get('recent_samples', [])[:limit]


# Module singleton
_health_checker = None


def get_health_checker() -> SystemHealthChecker:
    """Get or create global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = SystemHealthChecker()
    return _health_checker


# CLI for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\nTesting SystemHealthChecker...\n")

    checker = SystemHealthChecker()

    print("=" * 50)
    print("Log Scan:")
    print("=" * 50)
    log_results = checker.scan_logs_for_errors()
    print(f"  Errors found: {log_results['errors_found']}")
    print(f"  Files scanned: {log_results['files_scanned']}")
    if log_results['by_type']:
        print(f"  By type: {log_results['by_type']}")

    print("\n" + "=" * 50)
    print("Config Validation:")
    print("=" * 50)
    config_results = checker.validate_config()
    print(f"  Valid: {config_results['valid']}")
    print(f"  Checks passed: {config_results['checks_passed']}")
    if config_results['errors']:
        print(f"  Errors: {config_results['errors']}")
    if config_results['warnings']:
        print(f"  Warnings: {config_results['warnings']}")

    print("\n" + "=" * 50)
    print("Data Staleness:")
    print("=" * 50)
    staleness = checker.check_data_staleness()
    print(f"  Is stale: {staleness['is_stale']}")
    print(f"  Last trade: {staleness.get('last_trade_age_hours', 'N/A')}h ago")
    print(f"  Trades today: {staleness['trades_today']}")
    print(f"  Trades this week: {staleness['trades_this_week']}")

    print("\n" + "=" * 50)
    print("Telegram Summary:")
    print("=" * 50)
    print(checker.generate_telegram_summary())
    print("=" * 50)
