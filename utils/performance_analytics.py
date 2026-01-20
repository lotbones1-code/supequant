"""
Performance Analytics - Trade performance analysis and reporting

Reads from Trade Journal and calculates key metrics:
- Overall performance (win rate, PnL, profit factor)
- Breakdown by strategy
- Breakdown by close reason (tp1, tp2, sl, manual)
- Breakdown by confidence (when implemented)
- Time-based analysis

Usage:
    python utils/performance_analytics.py [days]
    
Example:
    python utils/performance_analytics.py 30  # Last 30 days
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from collections import defaultdict

# Handle import whether run as module or directly
try:
    from utils.trade_journal import TradeJournal
except ImportError:
    from trade_journal import TradeJournal

logger = logging.getLogger(__name__)


class PerformanceAnalytics:
    """
    Analytics engine for trade performance analysis.
    
    Reads from Trade Journal and generates comprehensive reports
    with breakdowns by strategy, confidence, close reason, and time.
    """
    
    def __init__(self, journal_path: str = "runs", output_path: str = "runs/analytics"):
        """
        Initialize analytics engine.
        
        Args:
            journal_path: Base path where trade journals are stored
            output_path: Path for analytics output files
        """
        self.journal = TradeJournal(base_path=journal_path, enabled=True)
        self.output_path = output_path
        
        # Ensure output directory exists
        try:
            os.makedirs(self.output_path, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create analytics output path: {e}")
    
    def load_trades(self, days: int = 30) -> List[Dict]:
        """
        Load trades from the last N days using TradeJournal.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of trade dictionaries
        """
        return self.journal.get_recent_trades(days=days)
    
    def calculate_metrics(self, trades: List[Dict]) -> Dict[str, Any]:
        """
        Calculate overall performance metrics.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Dictionary with performance metrics
        """
        if not trades:
            return self._empty_metrics()
        
        # Separate wins and losses
        wins = [t for t in trades if t.get('pnl_abs', 0) > 0]
        losses = [t for t in trades if t.get('pnl_abs', 0) <= 0]
        
        # Calculate totals
        total_pnl = sum(t.get('pnl_abs', 0) for t in trades)
        gross_profit = sum(t.get('pnl_abs', 0) for t in wins)
        gross_loss = abs(sum(t.get('pnl_abs', 0) for t in losses))
        
        # Calculate averages
        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0
        
        # Profit factor (handle division by zero)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        
        # Win rate
        win_rate = len(wins) / len(trades) if trades else 0
        
        # Average trade duration
        durations = [t.get('duration_seconds', 0) for t in trades if t.get('duration_seconds')]
        avg_duration_minutes = (sum(durations) / len(durations) / 60) if durations else 0
        
        # Calculate max drawdown (simplified - based on cumulative PnL)
        max_drawdown = self._calculate_max_drawdown(trades)
        
        # Expectancy (average PnL per trade)
        expectancy = total_pnl / len(trades) if trades else 0
        
        return {
            'total_trades': len(trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': round(win_rate, 4),
            'win_rate_pct': round(win_rate * 100, 2),
            'total_pnl': round(total_pnl, 2),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'inf',
            'expectancy': round(expectancy, 2),
            'max_drawdown': round(max_drawdown, 2),
            'avg_trade_duration_minutes': round(avg_duration_minutes, 2),
        }
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics structure"""
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'win_rate_pct': 0,
            'total_pnl': 0,
            'gross_profit': 0,
            'gross_loss': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'expectancy': 0,
            'max_drawdown': 0,
            'avg_trade_duration_minutes': 0,
        }
    
    def _calculate_max_drawdown(self, trades: List[Dict]) -> float:
        """
        Calculate maximum drawdown from trade sequence.
        
        Args:
            trades: List of trades sorted by time
            
        Returns:
            Maximum drawdown as positive number
        """
        if not trades:
            return 0
        
        # Sort by close time
        sorted_trades = sorted(trades, key=lambda t: t.get('timestamp_close', ''))
        
        cumulative_pnl = 0
        peak = 0
        max_drawdown = 0
        
        for trade in sorted_trades:
            cumulative_pnl += trade.get('pnl_abs', 0)
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            drawdown = peak - cumulative_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def calculate_metrics_by_confidence(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Break down metrics by confidence score ranges.
        
        Ranges:
        - high: 90-100%
        - medium: 70-89%
        - low: 50-69%
        - very_low: 0-49%
        - unknown: None/missing
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Dictionary with metrics for each confidence range
        """
        buckets = {
            'high': [],      # 90-100
            'medium': [],    # 70-89
            'low': [],       # 50-69
            'very_low': [],  # 0-49
            'unknown': [],   # None/missing
        }
        
        for trade in trades:
            confidence = trade.get('confidence_score')
            
            if confidence is None:
                buckets['unknown'].append(trade)
            elif confidence >= 90:
                buckets['high'].append(trade)
            elif confidence >= 70:
                buckets['medium'].append(trade)
            elif confidence >= 50:
                buckets['low'].append(trade)
            else:
                buckets['very_low'].append(trade)
        
        return {
            name: self._bucket_metrics(trades_list)
            for name, trades_list in buckets.items()
        }
    
    def calculate_metrics_by_strategy(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Break down metrics by strategy name.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Dictionary with metrics for each strategy
        """
        by_strategy = defaultdict(list)
        
        for trade in trades:
            strategy = trade.get('strategy_name', 'unknown')
            by_strategy[strategy].append(trade)
        
        return {
            name: self._bucket_metrics(trades_list)
            for name, trades_list in by_strategy.items()
        }
    
    def calculate_metrics_by_close_reason(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Break down metrics by close reason (tp1, tp2, sl, manual).
        
        This is useful NOW because close_reason is always populated.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Dictionary with metrics for each close reason
        """
        by_reason = defaultdict(list)
        
        for trade in trades:
            reason = trade.get('close_reason', 'unknown')
            by_reason[reason].append(trade)
        
        return {
            name: self._bucket_metrics(trades_list)
            for name, trades_list in by_reason.items()
        }
    
    def calculate_metrics_by_day_of_week(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Break down metrics by day of week.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            Dictionary with metrics for each day
        """
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        by_day = {day: [] for day in days}
        
        for trade in trades:
            timestamp = trade.get('timestamp_close')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    day_name = days[dt.weekday()]
                    by_day[day_name].append(trade)
                except:
                    pass
        
        return {
            name: self._bucket_metrics(trades_list)
            for name, trades_list in by_day.items()
            if trades_list  # Only include days with trades
        }
    
    def _bucket_metrics(self, trades: List[Dict]) -> Dict[str, Any]:
        """
        Calculate simplified metrics for a bucket of trades.
        
        Args:
            trades: List of trades in this bucket
            
        Returns:
            Metrics dictionary
        """
        if not trades:
            return {
                'trade_count': 0,
                'win_rate': 0,
                'win_rate_pct': 0,
                'avg_pnl': 0,
                'total_pnl': 0,
                'profit_factor': 0,
            }
        
        wins = [t for t in trades if t.get('pnl_abs', 0) > 0]
        losses = [t for t in trades if t.get('pnl_abs', 0) <= 0]
        
        total_pnl = sum(t.get('pnl_abs', 0) for t in trades)
        gross_profit = sum(t.get('pnl_abs', 0) for t in wins)
        gross_loss = abs(sum(t.get('pnl_abs', 0) for t in losses))
        
        win_rate = len(wins) / len(trades) if trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        
        return {
            'trade_count': len(trades),
            'win_rate': round(win_rate, 4),
            'win_rate_pct': round(win_rate * 100, 2),
            'avg_pnl': round(total_pnl / len(trades), 2),
            'total_pnl': round(total_pnl, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'inf',
        }
    
    def generate_report(self, days: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive analytics report.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Complete report dictionary
        """
        trades = self.load_trades(days=days)
        
        # Calculate date range
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)
        
        # Generate all breakdowns
        by_confidence = self.calculate_metrics_by_confidence(trades)
        by_strategy = self.calculate_metrics_by_strategy(trades)
        by_close_reason = self.calculate_metrics_by_close_reason(trades)
        by_day = self.calculate_metrics_by_day_of_week(trades)
        
        # Validate confidence correlation
        confidence_valid = self._validate_confidence_correlation(by_confidence)
        
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days,
            },
            'overall': self.calculate_metrics(trades),
            'by_confidence': by_confidence,
            'by_strategy': by_strategy,
            'by_close_reason': by_close_reason,
            'by_day_of_week': by_day,
            'validation': {
                'confidence_correlation_valid': confidence_valid,
                'note': 'True if higher confidence ranges have higher win rates (when data available)'
            }
        }
        
        return report
    
    def _validate_confidence_correlation(self, by_confidence: Dict) -> Optional[bool]:
        """
        Check if higher confidence correlates with higher win rate.
        
        Returns:
            True if correlation valid, False if not, None if insufficient data
        """
        # Get win rates for ranges that have data
        ranges = ['high', 'medium', 'low', 'very_low']
        win_rates = []
        
        for r in ranges:
            data = by_confidence.get(r, {})
            if data.get('trade_count', 0) >= 3:  # Need at least 3 trades
                win_rates.append((r, data.get('win_rate', 0)))
        
        if len(win_rates) < 2:
            return None  # Not enough data to validate
        
        # Check if win rates decrease as we go from high to low
        # This is a simplified check - just verify high > low if both exist
        high_wr = by_confidence.get('high', {}).get('win_rate', 0)
        low_wr = by_confidence.get('low', {}).get('win_rate', 0)
        
        if by_confidence.get('high', {}).get('trade_count', 0) >= 3 and \
           by_confidence.get('low', {}).get('trade_count', 0) >= 3:
            return high_wr > low_wr
        
        return None
    
    def save_report(self, report: Dict, filename: str = None) -> str:
        """
        Save report to runs/analytics/ as JSON.
        
        Args:
            report: Report dictionary
            filename: Optional filename (auto-generated if not provided)
            
        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"analytics_{timestamp}.json"
        
        filepath = os.path.join(self.output_path, filename)
        
        try:
            os.makedirs(self.output_path, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"📊 Analytics report saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            return ""
    
    def print_summary(self, report: Dict) -> None:
        """
        Print human-readable summary to console.
        
        Args:
            report: Report dictionary
        """
        period = report.get('period', {})
        overall = report.get('overall', {})
        by_confidence = report.get('by_confidence', {})
        by_strategy = report.get('by_strategy', {})
        by_close_reason = report.get('by_close_reason', {})
        validation = report.get('validation', {})
        
        print("\n" + "═" * 55)
        print("📊 PERFORMANCE ANALYTICS REPORT")
        print(f"Period: {period.get('start', 'N/A')} to {period.get('end', 'N/A')}")
        print("═" * 55)
        
        # Overall metrics
        print("\n📈 OVERALL METRICS:")
        print(f"   • Total Trades: {overall.get('total_trades', 0)}")
        print(f"   • Win Rate: {overall.get('win_rate_pct', 0)}%")
        print(f"   • Profit Factor: {overall.get('profit_factor', 0)}")
        print(f"   • Total PnL: ${overall.get('total_pnl', 0):+.2f}")
        print(f"   • Avg Win: ${overall.get('avg_win', 0):.2f}")
        print(f"   • Avg Loss: ${overall.get('avg_loss', 0):.2f}")
        print(f"   • Expectancy: ${overall.get('expectancy', 0):+.2f}/trade")
        print(f"   • Max Drawdown: ${overall.get('max_drawdown', 0):.2f}")
        print(f"   • Avg Duration: {overall.get('avg_trade_duration_minutes', 0):.1f} min")
        
        # By close reason (most useful now)
        if by_close_reason:
            print("\n🎯 BY CLOSE REASON:")
            print("┌─────────────┬────────┬──────────┬───────────┐")
            print("│ Reason      │ Trades │ Win Rate │ Total PnL │")
            print("├─────────────┼────────┼──────────┼───────────┤")
            for reason, data in sorted(by_close_reason.items()):
                if data.get('trade_count', 0) > 0:
                    print(f"│ {reason:<11} │ {data.get('trade_count', 0):>6} │ {data.get('win_rate_pct', 0):>7.1f}% │ ${data.get('total_pnl', 0):>+8.2f} │")
            print("└─────────────┴────────┴──────────┴───────────┘")
        
        # By strategy
        if by_strategy:
            print("\n📋 BY STRATEGY:")
            print("┌─────────────────────┬────────┬──────────┬───────────┐")
            print("│ Strategy            │ Trades │ Win Rate │ Total PnL │")
            print("├─────────────────────┼────────┼──────────┼───────────┤")
            for strategy, data in sorted(by_strategy.items()):
                if data.get('trade_count', 0) > 0:
                    name = strategy[:19] if len(strategy) > 19 else strategy
                    print(f"│ {name:<19} │ {data.get('trade_count', 0):>6} │ {data.get('win_rate_pct', 0):>7.1f}% │ ${data.get('total_pnl', 0):>+8.2f} │")
            print("└─────────────────────┴────────┴──────────┴───────────┘")
        
        # By confidence (may be empty until confidence sizing implemented)
        has_confidence_data = any(
            by_confidence.get(level, {}).get('trade_count', 0) > 0 
            for level in ['high', 'medium', 'low', 'very_low']
        )
        
        if has_confidence_data:
            print("\n🎚️  BY CONFIDENCE LEVEL:")
            print("┌─────────────────┬────────┬──────────┬───────────┐")
            print("│ Confidence      │ Trades │ Win Rate │ Total PnL │")
            print("├─────────────────┼────────┼──────────┼───────────┤")
            confidence_order = ['high', 'medium', 'low', 'very_low']
            labels = {'high': 'High (90%+)', 'medium': 'Medium (70-89%)', 'low': 'Low (50-69%)', 'very_low': 'Very Low (<50%)'}
            for level in confidence_order:
                data = by_confidence.get(level, {})
                if data.get('trade_count', 0) > 0:
                    print(f"│ {labels[level]:<15} │ {data.get('trade_count', 0):>6} │ {data.get('win_rate_pct', 0):>7.1f}% │ ${data.get('total_pnl', 0):>+8.2f} │")
            print("└─────────────────┴────────┴──────────┴───────────┘")
        else:
            unknown_count = by_confidence.get('unknown', {}).get('trade_count', 0)
            if unknown_count > 0:
                print(f"\n🎚️  CONFIDENCE: {unknown_count} trades with no confidence score")
                print("   (Confidence scoring not yet implemented)")
        
        # Validation
        conf_valid = validation.get('confidence_correlation_valid')
        if conf_valid is True:
            print("\n✅ VALIDATION: Higher confidence = Higher win rate (CONFIRMED)")
        elif conf_valid is False:
            print("\n⚠️  VALIDATION: Confidence correlation NOT confirmed")
        else:
            print("\n📊 VALIDATION: Insufficient data for confidence correlation")
        
        print("\n" + "═" * 55 + "\n")


# CLI Runner
if __name__ == "__main__":
    import sys
    
    # Setup basic logging for CLI
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # Parse days argument
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    
    print(f"\n📊 Analyzing last {days} days of trades...\n")
    
    # Run analytics
    analytics = PerformanceAnalytics()
    report = analytics.generate_report(days=days)
    
    # Print summary
    analytics.print_summary(report)
    
    # Save report
    path = analytics.save_report(report)
    if path:
        print(f"📁 Report saved to: {path}")
