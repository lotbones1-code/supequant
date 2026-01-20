"""
Trade Quality Inspector - Phase 1.5 Module 4

Analyzes quality and patterns of completed trades.
READ-ONLY - Does not affect trading decisions.

Provides:
- Hourly performance analysis
- Trade duration analysis
- Close reason breakdown (TP1/TP2/SL)
- Strategy comparison

Usage:
    from utils.trade_quality import TradeQualityInspector
    
    inspector = TradeQualityInspector()
    print(inspector.generate_report())
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


class TradeQualityInspector:
    """
    Analyze quality and patterns of completed trades.
    
    This is READ-ONLY analytics - does NOT affect trading decisions.
    All calculations are informational for pattern discovery.
    """
    
    # Minimum trades for meaningful analysis
    MIN_TRADES_PER_CATEGORY = 3
    
    def __init__(self, trade_journal_path: str = 'runs'):
        """
        Initialize the trade quality inspector.
        
        Args:
            trade_journal_path: Path to trade journal files
        """
        self.trade_journal_path = trade_journal_path
        self.trades = self._load_trades()
        
        logger.info(f"📊 TradeQualityInspector initialized ({len(self.trades)} trades loaded)")
    
    def _load_trades(self, days: int = 30) -> List[Dict]:
        """
        Load trades from TradeJournal JSONL files.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of trade dictionaries
        """
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
        
        return trades
    
    def _parse_timestamp(self, trade: Dict) -> Optional[datetime]:
        """Parse timestamp from trade, preferring entry time."""
        # Try entry time first, then close time
        for field in ['timestamp_entry', 'timestamp_close']:
            ts = trade.get(field)
            if ts:
                try:
                    # Handle both with and without timezone
                    if ts.endswith('Z'):
                        ts = ts.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    pass
        return None
    
    def _is_winning_trade(self, trade: Dict) -> bool:
        """Check if trade was a winner."""
        return trade.get('pnl_abs', 0) > 0
    
    def analyze_trade_by_hour(self) -> Dict[str, Any]:
        """
        Group trades by entry hour (UTC) and calculate win rates.
        
        Returns:
            Dict with hourly statistics
        """
        if not self.trades:
            return {
                'has_data': False,
                'message': 'No trades to analyze'
            }
        
        # Group by hour
        hourly_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0})
        
        for trade in self.trades:
            ts = self._parse_timestamp(trade)
            if not ts:
                continue
            
            hour = ts.hour
            hourly_stats[hour]['trades'] += 1
            hourly_stats[hour]['total_pnl'] += trade.get('pnl_abs', 0)
            
            if self._is_winning_trade(trade):
                hourly_stats[hour]['wins'] += 1
            else:
                hourly_stats[hour]['losses'] += 1
        
        if not hourly_stats:
            return {
                'has_data': False,
                'message': 'No trades with valid timestamps'
            }
        
        # Calculate win rates and format
        formatted_stats = {}
        for hour, stats in hourly_stats.items():
            win_rate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
            formatted_stats[hour] = {
                'trades': stats['trades'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'win_rate': round(win_rate, 1),
                'total_pnl': round(stats['total_pnl'], 2),
                'avg_pnl': round(stats['total_pnl'] / stats['trades'], 2) if stats['trades'] > 0 else 0
            }
        
        # Find best/worst hours (minimum trades threshold)
        qualified_hours = [(h, s) for h, s in formatted_stats.items() 
                          if s['trades'] >= self.MIN_TRADES_PER_CATEGORY]
        
        best_hours = sorted(qualified_hours, key=lambda x: x[1]['win_rate'], reverse=True)[:3]
        worst_hours = sorted(qualified_hours, key=lambda x: x[1]['win_rate'])[:3]
        
        return {
            'has_data': True,
            'hourly_stats': dict(sorted(formatted_stats.items())),
            'best_hours': [(h, s['win_rate'], s['trades']) for h, s in best_hours],
            'worst_hours': [(h, s['win_rate'], s['trades']) for h, s in worst_hours],
            'total_hours_traded': len(formatted_stats)
        }
    
    def analyze_trade_by_duration(self) -> Dict[str, Any]:
        """
        Group trades by duration buckets.
        
        Buckets:
        - quick: <15 minutes (900 seconds)
        - medium: 15-60 minutes (900-3600 seconds)
        - long: >60 minutes (3600+ seconds)
        
        Returns:
            Dict with duration statistics
        """
        if not self.trades:
            return {
                'has_data': False,
                'message': 'No trades to analyze'
            }
        
        buckets = {
            'quick': {'label': '<15 min', 'trades': 0, 'wins': 0, 'total_pnl': 0, 'durations': []},
            'medium': {'label': '15-60 min', 'trades': 0, 'wins': 0, 'total_pnl': 0, 'durations': []},
            'long': {'label': '>60 min', 'trades': 0, 'wins': 0, 'total_pnl': 0, 'durations': []}
        }
        
        for trade in self.trades:
            duration = trade.get('duration_seconds', 0)
            if duration <= 0:
                continue
            
            # Determine bucket
            if duration < 900:  # <15 min
                bucket = 'quick'
            elif duration < 3600:  # 15-60 min
                bucket = 'medium'
            else:  # >60 min
                bucket = 'long'
            
            buckets[bucket]['trades'] += 1
            buckets[bucket]['total_pnl'] += trade.get('pnl_abs', 0)
            buckets[bucket]['durations'].append(duration)
            
            if self._is_winning_trade(trade):
                buckets[bucket]['wins'] += 1
        
        # Calculate stats for each bucket
        duration_stats = {}
        for bucket_name, data in buckets.items():
            if data['trades'] > 0:
                win_rate = (data['wins'] / data['trades'] * 100)
                avg_duration = sum(data['durations']) / len(data['durations']) / 60  # in minutes
                duration_stats[bucket_name] = {
                    'label': data['label'],
                    'trades': data['trades'],
                    'wins': data['wins'],
                    'losses': data['trades'] - data['wins'],
                    'win_rate': round(win_rate, 1),
                    'total_pnl': round(data['total_pnl'], 2),
                    'avg_pnl': round(data['total_pnl'] / data['trades'], 2),
                    'avg_duration_min': round(avg_duration, 1)
                }
        
        if not duration_stats:
            return {
                'has_data': False,
                'message': 'No trades with valid duration'
            }
        
        # Find best duration
        best_bucket = max(duration_stats.items(), key=lambda x: x[1]['win_rate'])
        
        return {
            'has_data': True,
            'duration_stats': duration_stats,
            'best_duration': best_bucket[0],
            'best_duration_win_rate': best_bucket[1]['win_rate']
        }
    
    def analyze_by_close_reason(self) -> Dict[str, Any]:
        """
        Group trades by how they closed (TP1, TP2, SL, manual).
        
        Returns:
            Dict with close reason statistics
        """
        if not self.trades:
            return {
                'has_data': False,
                'message': 'No trades to analyze'
            }
        
        reason_stats = defaultdict(lambda: {'trades': 0, 'total_pnl': 0, 'pnl_list': []})
        
        for trade in self.trades:
            reason = trade.get('close_reason', 'unknown')
            if not reason:
                reason = 'unknown'
            reason = reason.lower()
            
            reason_stats[reason]['trades'] += 1
            pnl = trade.get('pnl_abs', 0)
            reason_stats[reason]['total_pnl'] += pnl
            reason_stats[reason]['pnl_list'].append(pnl)
        
        if not reason_stats:
            return {
                'has_data': False,
                'message': 'No trades with close reason'
            }
        
        # Calculate stats
        formatted_stats = {}
        total_trades = sum(s['trades'] for s in reason_stats.values())
        
        for reason, stats in reason_stats.items():
            pct_of_trades = (stats['trades'] / total_trades * 100) if total_trades > 0 else 0
            avg_pnl = stats['total_pnl'] / stats['trades'] if stats['trades'] > 0 else 0
            
            formatted_stats[reason] = {
                'trades': stats['trades'],
                'pct_of_trades': round(pct_of_trades, 1),
                'total_pnl': round(stats['total_pnl'], 2),
                'avg_pnl': round(avg_pnl, 2),
                'min_pnl': round(min(stats['pnl_list']), 2) if stats['pnl_list'] else 0,
                'max_pnl': round(max(stats['pnl_list']), 2) if stats['pnl_list'] else 0
            }
        
        # Calculate TP/SL rates
        tp_trades = sum(s['trades'] for r, s in reason_stats.items() if 'tp' in r)
        sl_trades = reason_stats.get('sl', {}).get('trades', 0)
        
        return {
            'has_data': True,
            'reason_stats': dict(sorted(formatted_stats.items())),
            'total_trades': total_trades,
            'tp_hit_rate': round((tp_trades / total_trades * 100), 1) if total_trades > 0 else 0,
            'sl_hit_rate': round((sl_trades / total_trades * 100), 1) if total_trades > 0 else 0,
            'tp1_rate': round((reason_stats.get('tp1', {}).get('trades', 0) / total_trades * 100), 1) if total_trades > 0 else 0,
            'tp2_rate': round((reason_stats.get('tp2', {}).get('trades', 0) / total_trades * 100), 1) if total_trades > 0 else 0
        }
    
    def analyze_by_strategy(self) -> Dict[str, Any]:
        """
        Group trades by strategy name.
        
        Returns:
            Dict with strategy statistics
        """
        if not self.trades:
            return {
                'has_data': False,
                'message': 'No trades to analyze'
            }
        
        strategy_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_pnl': 0})
        
        for trade in self.trades:
            strategy = trade.get('strategy_name', 'unknown')
            if not strategy:
                strategy = 'unknown'
            
            strategy_stats[strategy]['trades'] += 1
            strategy_stats[strategy]['total_pnl'] += trade.get('pnl_abs', 0)
            
            if self._is_winning_trade(trade):
                strategy_stats[strategy]['wins'] += 1
        
        if not strategy_stats:
            return {
                'has_data': False,
                'message': 'No trades with strategy data'
            }
        
        # Calculate stats
        formatted_stats = {}
        for strategy, stats in strategy_stats.items():
            win_rate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
            formatted_stats[strategy] = {
                'trades': stats['trades'],
                'wins': stats['wins'],
                'losses': stats['trades'] - stats['wins'],
                'win_rate': round(win_rate, 1),
                'total_pnl': round(stats['total_pnl'], 2),
                'avg_pnl': round(stats['total_pnl'] / stats['trades'], 2) if stats['trades'] > 0 else 0
            }
        
        # Find best strategy (minimum trades)
        qualified = [(s, d) for s, d in formatted_stats.items() 
                    if d['trades'] >= self.MIN_TRADES_PER_CATEGORY]
        
        best_strategy = None
        if qualified:
            best = max(qualified, key=lambda x: x[1]['win_rate'])
            best_strategy = best[0]
        
        return {
            'has_data': True,
            'strategy_stats': dict(sorted(formatted_stats.items(), 
                                         key=lambda x: x[1]['win_rate'], reverse=True)),
            'best_strategy': best_strategy,
            'total_strategies': len(formatted_stats)
        }
    
    def analyze_by_side(self) -> Dict[str, Any]:
        """
        Compare LONG vs SHORT performance.
        
        Returns:
            Dict with side statistics
        """
        if not self.trades:
            return {
                'has_data': False,
                'message': 'No trades to analyze'
            }
        
        side_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_pnl': 0})
        
        for trade in self.trades:
            side = trade.get('side', 'unknown')
            if not side:
                side = 'unknown'
            side = side.lower()
            
            side_stats[side]['trades'] += 1
            side_stats[side]['total_pnl'] += trade.get('pnl_abs', 0)
            
            if self._is_winning_trade(trade):
                side_stats[side]['wins'] += 1
        
        # Calculate stats
        formatted_stats = {}
        for side, stats in side_stats.items():
            win_rate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
            formatted_stats[side] = {
                'trades': stats['trades'],
                'wins': stats['wins'],
                'losses': stats['trades'] - stats['wins'],
                'win_rate': round(win_rate, 1),
                'total_pnl': round(stats['total_pnl'], 2)
            }
        
        return {
            'has_data': True,
            'side_stats': formatted_stats
        }
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall trade statistics."""
        if not self.trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0
            }
        
        wins = sum(1 for t in self.trades if self._is_winning_trade(t))
        total_pnl = sum(t.get('pnl_abs', 0) for t in self.trades)
        
        return {
            'total_trades': len(self.trades),
            'wins': wins,
            'losses': len(self.trades) - wins,
            'win_rate': round((wins / len(self.trades) * 100), 1) if self.trades else 0,
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(total_pnl / len(self.trades), 2) if self.trades else 0
        }
    
    def generate_report(self) -> str:
        """
        Generate formatted trade quality report.
        
        Returns:
            Beautifully formatted report string
        """
        overall = self.get_overall_stats()
        hourly = self.analyze_trade_by_hour()
        duration = self.analyze_trade_by_duration()
        close_reason = self.analyze_by_close_reason()
        strategy = self.analyze_by_strategy()
        side = self.analyze_by_side()
        
        def pad(content: str) -> str:
            return f"║ {content.ljust(58)} ║"
        
        def status_icon(win_rate: float) -> str:
            if win_rate >= 60:
                return '✅'
            elif win_rate >= 50:
                return '🟡'
            else:
                return '❌'
        
        lines = []
        lines.append("╔════════════════════════════════════════════════════════════╗")
        lines.append("║              TRADE QUALITY ANALYSIS                        ║")
        lines.append(pad(f"Based on {overall['total_trades']} trades (last 30 days)"))
        lines.append(pad(f"Overall: {overall['win_rate']}% win rate | ${overall['total_pnl']:.2f} PnL"))
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Hourly Analysis
        lines.append(pad("TRADING HOURS (UTC)"))
        if hourly.get('has_data') and hourly.get('best_hours'):
            for hour, win_rate, trades in hourly['best_hours'][:2]:
                icon = status_icon(win_rate)
                lines.append(pad(f"  {icon} Best:  {hour:02d}:00 - {win_rate}% win rate ({trades} trades)"))
            for hour, win_rate, trades in hourly['worst_hours'][:2]:
                icon = status_icon(win_rate)
                lines.append(pad(f"  {icon} Worst: {hour:02d}:00 - {win_rate}% win rate ({trades} trades)"))
        else:
            lines.append(pad("  Not enough data per hour yet"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Duration Analysis
        lines.append(pad("TRADE DURATION"))
        if duration.get('has_data'):
            for bucket in ['quick', 'medium', 'long']:
                if bucket in duration['duration_stats']:
                    d = duration['duration_stats'][bucket]
                    icon = status_icon(d['win_rate'])
                    lines.append(pad(f"  {icon} {d['label']:>10}: {d['win_rate']}% win rate ({d['trades']} trades)"))
        else:
            lines.append(pad("  Not enough data yet"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Close Reason Analysis
        lines.append(pad("EXIT ANALYSIS"))
        if close_reason.get('has_data'):
            for reason, stats in close_reason['reason_stats'].items():
                pnl_sign = '+' if stats['avg_pnl'] >= 0 else ''
                lines.append(pad(f"  {reason.upper():>8}: {stats['pct_of_trades']}% ({stats['trades']} trades) avg {pnl_sign}${stats['avg_pnl']:.2f}"))
            lines.append(pad(f"  TP Hit Rate: {close_reason['tp_hit_rate']}% | SL Hit Rate: {close_reason['sl_hit_rate']}%"))
        else:
            lines.append(pad("  Not enough data yet"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Strategy Analysis
        lines.append(pad("STRATEGY PERFORMANCE"))
        if strategy.get('has_data'):
            for strat_name, stats in list(strategy['strategy_stats'].items())[:3]:
                icon = status_icon(stats['win_rate'])
                pnl_sign = '+' if stats['total_pnl'] >= 0 else ''
                lines.append(pad(f"  {icon} {strat_name[:15]:>15}: {stats['win_rate']}% ({stats['trades']} trades) {pnl_sign}${stats['total_pnl']:.2f}"))
        else:
            lines.append(pad("  Not enough data yet"))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Recommendations
        lines.append(pad("RECOMMENDATIONS"))
        recommendations = self._generate_recommendations(hourly, duration, close_reason, strategy)
        for rec in recommendations[:3]:
            lines.append(pad(f"  {rec}"))
        if not recommendations:
            lines.append(pad("  Need more trades for recommendations"))
        
        lines.append("╚════════════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)
    
    def _generate_recommendations(self, hourly: Dict, duration: Dict, 
                                  close_reason: Dict, strategy: Dict) -> List[str]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Hourly recommendation
        if hourly.get('has_data') and hourly.get('best_hours'):
            best_hour = hourly['best_hours'][0]
            if best_hour[1] >= 60:  # >60% win rate
                recommendations.append(f"📌 Best hours: {best_hour[0]:02d}:00 UTC ({best_hour[1]}% win rate)")
        
        # Duration recommendation
        if duration.get('has_data') and duration.get('best_duration'):
            best_dur = duration['duration_stats'].get(duration['best_duration'])
            if best_dur and best_dur['win_rate'] >= 55:
                recommendations.append(f"📌 {best_dur['label']} trades perform best ({best_dur['win_rate']}%)")
        
        # TP/SL recommendation
        if close_reason.get('has_data'):
            tp_rate = close_reason.get('tp_hit_rate', 0)
            sl_rate = close_reason.get('sl_hit_rate', 0)
            if tp_rate >= 60:
                recommendations.append(f"📌 TP system working well ({tp_rate}% hit rate)")
            elif sl_rate >= 50:
                recommendations.append(f"⚠️ High SL rate ({sl_rate}%) - review entry timing")
        
        # Strategy recommendation
        if strategy.get('has_data') and strategy.get('best_strategy'):
            best_strat = strategy['strategy_stats'].get(strategy['best_strategy'])
            if best_strat and best_strat['win_rate'] >= 55:
                recommendations.append(f"📌 {strategy['best_strategy']} strategy outperforming")
        
        return recommendations
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary dict for API/dashboard use.
        
        Returns:
            Dict with all analysis results
        """
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'overall': self.get_overall_stats(),
            'hourly': self.analyze_trade_by_hour(),
            'duration': self.analyze_trade_by_duration(),
            'close_reason': self.analyze_by_close_reason(),
            'strategy': self.analyze_by_strategy(),
            'side': self.analyze_by_side()
        }


# CLI for testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    print("\n📊 Trade Quality Analysis Test\n")
    
    inspector = TradeQualityInspector()
    
    # Print report
    print(inspector.generate_report())
    
    # Print summary
    print("\n📋 Summary:")
    summary = inspector.get_summary()
    print(f"   Total trades: {summary['overall']['total_trades']}")
    print(f"   Win rate: {summary['overall']['win_rate']}%")
    print(f"   Total PnL: ${summary['overall']['total_pnl']:.2f}")
    
    print("\n✅ Trade Quality Inspector test complete!")
