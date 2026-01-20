"""
Filter Effectiveness Scorer - Phase 1.5 Module 2

Analyzes the effectiveness of each trading filter by examining
trade outcomes and calculating precision metrics.

Usage:
    from utils.filter_scorer import FilterScorer
    
    scorer = FilterScorer()
    print(scorer.generate_report())

Note: Requires trades to have 'filters_passed' field (added in Phase 1.5).
      Older trades without this field are handled gracefully.
"""

import os
import sys
import json
import glob
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class FilterScorer:
    """
    Analyze and score the effectiveness of trading filters.
    
    For each filter, calculates:
    - Rejection rate: How often this filter rejects trades
    - Precision: Win rate of trades that passed this filter
    - Contribution: How much this filter improves over baseline win rate
    - Recommendation: KEEP, ADJUST, or DISABLE
    """
    
    def __init__(self, trade_journal_path: str = 'runs'):
        """
        Initialize the filter scorer.
        
        Args:
            trade_journal_path: Base path for trade journal files
        """
        self.trade_journal_path = trade_journal_path
        self.trades = self._load_trades()
        self._overall_stats = None
    
    def _load_trades(self, days: int = 30) -> List[Dict]:
        """
        Load trades from the last N days of JSONL files.
        
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
                        continue  # Skip old files
                except ValueError:
                    pass  # Not a date-formatted directory, include it
                
                # Read JSONL file
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                trade = json.loads(line)
                                trades.append(trade)
                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON in {filepath}")
                                
            except Exception as e:
                logger.warning(f"Error reading {filepath}: {e}")
        
        logger.info(f"Loaded {len(trades)} trades from last {days} days")
        return trades
    
    def _get_overall_stats(self) -> Dict[str, Any]:
        """Calculate overall trading statistics (cached)."""
        if self._overall_stats is not None:
            return self._overall_stats
        
        if not self.trades:
            self._overall_stats = {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0
            }
            return self._overall_stats
        
        wins = sum(1 for t in self.trades if t.get('pnl_abs', 0) > 0)
        losses = len(self.trades) - wins
        total_pnl = sum(t.get('pnl_abs', 0) for t in self.trades)
        
        self._overall_stats = {
            'total_trades': len(self.trades),
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / len(self.trades) * 100) if self.trades else 0,
            'total_pnl': total_pnl
        }
        return self._overall_stats
    
    def score_filter(self, filter_name: str) -> Dict[str, Any]:
        """
        Analyze effectiveness of a single filter.
        
        Args:
            filter_name: Name of the filter to analyze
            
        Returns:
            Dict with filter statistics and recommendation
        """
        overall = self._get_overall_stats()
        
        if not self.trades:
            return self._empty_filter_score(filter_name)
        
        # Count trades that passed this filter
        trades_with_filter = []
        trades_without_filter = []
        
        for trade in self.trades:
            filters_passed = trade.get('filters_passed', [])
            if filters_passed is None:
                filters_passed = []
            
            if filter_name in filters_passed:
                trades_with_filter.append(trade)
            else:
                # Trade either rejected by this filter OR filter data not available
                trades_without_filter.append(trade)
        
        # If no trades have filter data, we can't analyze
        total_with_data = sum(1 for t in self.trades if t.get('filters_passed'))
        if total_with_data == 0:
            return {
                'filter_name': filter_name,
                'status': 'no_data',
                'status_icon': '⚪',
                'message': 'No filter data available (trades before Phase 1.5)',
                'recommendation': 'WAIT - Need more data'
            }
        
        # Calculate metrics
        accepted_count = len(trades_with_filter)
        rejected_count = total_with_data - accepted_count
        
        if accepted_count == 0:
            return {
                'filter_name': filter_name,
                'total_trades_analyzed': total_with_data,
                'trades_accepted': 0,
                'trades_rejected': rejected_count,
                'rejection_rate': 100.0,
                'wins_in_accepted': 0,
                'precision': 0.0,
                'overall_win_rate': overall['win_rate'],
                'contribution': 0.0,
                'pnl_contribution': 0.0,
                'status': 'low_data',
                'status_icon': '⚪',
                'recommendation': 'WAIT - No accepted trades'
            }
        
        # Calculate precision (win rate of accepted trades)
        wins_in_accepted = sum(1 for t in trades_with_filter if t.get('pnl_abs', 0) > 0)
        precision = (wins_in_accepted / accepted_count * 100) if accepted_count > 0 else 0
        
        # Calculate contribution (improvement over baseline)
        contribution = precision - overall['win_rate']
        
        # Calculate PnL contribution
        pnl_accepted = sum(t.get('pnl_abs', 0) for t in trades_with_filter)
        
        # Calculate rejection rate
        rejection_rate = (rejected_count / total_with_data * 100) if total_with_data > 0 else 0
        
        # Determine recommendation
        status, status_icon, recommendation = self._get_recommendation(
            precision, contribution, accepted_count
        )
        
        return {
            'filter_name': filter_name,
            'total_trades_analyzed': total_with_data,
            'trades_accepted': accepted_count,
            'trades_rejected': rejected_count,
            'rejection_rate': round(rejection_rate, 1),
            'wins_in_accepted': wins_in_accepted,
            'precision': round(precision, 1),
            'overall_win_rate': round(overall['win_rate'], 1),
            'contribution': round(contribution, 1),
            'pnl_contribution': round(pnl_accepted, 2),
            'status': status,
            'status_icon': status_icon,
            'recommendation': recommendation
        }
    
    def _empty_filter_score(self, filter_name: str) -> Dict[str, Any]:
        """Return empty score for when no trades exist."""
        return {
            'filter_name': filter_name,
            'total_trades_analyzed': 0,
            'trades_accepted': 0,
            'trades_rejected': 0,
            'rejection_rate': 0.0,
            'wins_in_accepted': 0,
            'precision': 0.0,
            'overall_win_rate': 0.0,
            'contribution': 0.0,
            'pnl_contribution': 0.0,
            'status': 'no_data',
            'status_icon': '⚪',
            'recommendation': 'WAIT - No trade data'
        }
    
    def _get_recommendation(self, precision: float, contribution: float, 
                           sample_size: int) -> tuple:
        """
        Determine recommendation based on metrics.
        
        Returns:
            (status, status_icon, recommendation)
        """
        # Need minimum sample size for reliable recommendation
        if sample_size < 5:
            return ('low_data', '⚪', 'WAIT - Need more trades (min 5)')
        
        # High performers
        if precision >= 70 and contribution > 10:
            return ('excellent', '✅', 'KEEP - Highly Effective')
        
        if precision >= 70:
            return ('good', '✅', 'KEEP - Good Performance')
        
        # Moderate performers
        if precision >= 55 and contribution >= 0:
            return ('moderate', '🟡', 'KEEP - Moderately Effective')
        
        if precision >= 55:
            return ('moderate', '🟡', 'MONITOR - Slight drag on performance')
        
        # Needs attention
        if precision >= 50:
            return ('warning', '⚠️', 'ADJUST - Thresholds may need tuning')
        
        # Poor performers
        return ('poor', '❌', 'DISABLE - Hurting performance')
    
    def score_all_filters(self) -> Dict[str, Dict]:
        """
        Score all filters found in trade data.
        
        Returns:
            Dict mapping filter names to their scores
        """
        # Collect all unique filter names
        all_filters = set()
        for trade in self.trades:
            filters_passed = trade.get('filters_passed', [])
            if filters_passed:
                all_filters.update(filters_passed)
        
        # Score each filter
        scores = {}
        for filter_name in sorted(all_filters):
            scores[filter_name] = self.score_filter(filter_name)
        
        return scores
    
    def identify_ineffective_filters(self, precision_threshold: float = 50.0) -> List[Dict]:
        """
        Find filters performing below threshold.
        
        Args:
            precision_threshold: Minimum acceptable precision (%)
            
        Returns:
            List of underperforming filter scores, sorted by precision
        """
        all_scores = self.score_all_filters()
        
        ineffective = []
        for name, score in all_scores.items():
            if score.get('status') == 'no_data':
                continue
            if score.get('precision', 100) < precision_threshold:
                ineffective.append(score)
        
        # Sort by precision (worst first)
        ineffective.sort(key=lambda x: x.get('precision', 0))
        
        return ineffective
    
    def get_filter_impact(self, filter_name: str) -> Dict[str, Any]:
        """
        Calculate the specific PnL impact of a filter.
        
        Args:
            filter_name: Name of the filter
            
        Returns:
            Dict with PnL impact metrics
        """
        score = self.score_filter(filter_name)
        overall = self._get_overall_stats()
        
        if score.get('status') == 'no_data' or score.get('trades_accepted', 0) == 0:
            return {
                'filter_name': filter_name,
                'has_data': False,
                'message': 'Insufficient data'
            }
        
        # Calculate what PnL would look like if this filter was disabled
        # (all trades that passed would still occur)
        accepted_pnl = score['pnl_contribution']
        
        # Average PnL per accepted trade
        avg_pnl_accepted = accepted_pnl / score['trades_accepted'] if score['trades_accepted'] > 0 else 0
        
        return {
            'filter_name': filter_name,
            'has_data': True,
            'trades_passed': score['trades_accepted'],
            'total_pnl_from_passed': round(accepted_pnl, 2),
            'avg_pnl_per_trade': round(avg_pnl_accepted, 2),
            'precision': score['precision'],
            'contribution_vs_baseline': score['contribution']
        }
    
    def generate_report(self) -> str:
        """
        Generate a formatted effectiveness report.
        
        Returns:
            Beautifully formatted report string
        """
        overall = self._get_overall_stats()
        all_scores = self.score_all_filters()
        ineffective = self.identify_ineffective_filters()
        
        # Helper for padding lines to 60 chars
        def pad_line(content: str) -> str:
            # Account for unicode box chars (║ takes 1 char visually)
            inner = content.ljust(58)
            return f"║ {inner} ║"
        
        lines = []
        lines.append("╔════════════════════════════════════════════════════════════╗")
        lines.append("║           FILTER EFFECTIVENESS ANALYSIS                    ║")
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Overall stats
        total_pnl = overall['total_pnl']
        pnl_str = f"${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"
        
        lines.append(pad_line(f"Based on: {overall['total_trades']} trades (last 30 days)"))
        lines.append(pad_line(f"Overall Win Rate: {overall['win_rate']:.1f}%"))
        lines.append(pad_line(f"Total PnL: {pnl_str}"))
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        if not all_scores:
            lines.append(pad_line(""))
            lines.append(pad_line("No filter data available yet."))
            lines.append(pad_line("Trades need 'filters_passed' field (Phase 1.5+)"))
            lines.append(pad_line(""))
        else:
            # Individual filter scores
            for name, score in sorted(all_scores.items(), key=lambda x: x[1].get('precision', 0), reverse=True):
                icon = score.get('status_icon', '⚪')
                
                if score.get('status') == 'no_data':
                    lines.append(pad_line(f"{icon} {name[:25]}"))
                    lines.append(pad_line("    No data available"))
                else:
                    lines.append(pad_line(f"{icon} {name[:25]}"))
                    lines.append(pad_line(f"    Rejection Rate: {score['rejection_rate']:.1f}%"))
                    lines.append(pad_line(f"    Precision: {score['precision']:.1f}%"))
                    lines.append(pad_line(f"    Contribution: {score['contribution']:+.1f}%"))
                    rec = score['recommendation'][:40]
                    lines.append(pad_line(f"    Recommendation: {rec}"))
                lines.append(pad_line(""))
        
        lines.append("╠════════════════════════════════════════════════════════════╣")
        
        # Ineffective filters section
        if ineffective:
            lines.append(pad_line("⚠️  FILTERS NEEDING ATTENTION:"))
            for score in ineffective[:5]:  # Top 5 worst
                fname = score['filter_name'][:20]
                lines.append(pad_line(f"  {score['status_icon']} {fname}: {score['precision']:.1f}% precision"))
        else:
            lines.append(pad_line("✅ All filters performing above threshold"))
        
        lines.append("╚════════════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary dict for API/dashboard use.
        
        Returns:
            Summary dict with key metrics
        """
        overall = self._get_overall_stats()
        all_scores = self.score_all_filters()
        ineffective = self.identify_ineffective_filters()
        
        # Count by status
        status_counts = defaultdict(int)
        for score in all_scores.values():
            status_counts[score.get('status', 'unknown')] += 1
        
        return {
            'total_trades_analyzed': overall['total_trades'],
            'overall_win_rate': overall['win_rate'],
            'total_pnl': overall['total_pnl'],
            'filters_analyzed': len(all_scores),
            'filters_effective': status_counts.get('excellent', 0) + status_counts.get('good', 0),
            'filters_moderate': status_counts.get('moderate', 0),
            'filters_warning': status_counts.get('warning', 0),
            'filters_poor': status_counts.get('poor', 0),
            'filters_no_data': status_counts.get('no_data', 0) + status_counts.get('low_data', 0),
            'ineffective_filters': [f['filter_name'] for f in ineffective],
            'all_scores': all_scores
        }


# CLI for testing
if __name__ == "__main__":
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    print("\n📊 Filter Effectiveness Analysis\n")
    
    scorer = FilterScorer()
    
    # Print report
    print(scorer.generate_report())
    
    # Print summary
    print("\n📋 Summary:")
    summary = scorer.get_summary()
    print(f"   Trades analyzed: {summary['total_trades_analyzed']}")
    print(f"   Filters analyzed: {summary['filters_analyzed']}")
    print(f"   Effective: {summary['filters_effective']}")
    print(f"   Moderate: {summary['filters_moderate']}")
    print(f"   Warning: {summary['filters_warning']}")
    print(f"   Poor: {summary['filters_poor']}")
    
    if summary['ineffective_filters']:
        print(f"\n   ⚠️ Ineffective filters: {', '.join(summary['ineffective_filters'])}")
    else:
        print(f"\n   ✅ All filters performing well!")
    
    print("\n✅ Filter Scorer test complete!")
