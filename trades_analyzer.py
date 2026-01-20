#!/usr/bin/env python3
"""
Trades Analyzer
Pattern recognition on wins/losses with comprehensive metrics tracking

Analyzes trade patterns to identify:
- Winning vs losing patterns
- Best/worst trading hours
- Volume patterns that predict success
- RSI levels that work best
- Consolidation patterns that lead to wins

Usage:
    python trades_analyzer.py --backtest-file backtesting/reports/results_*.json
    python trades_analyzer.py --analyze-all  # Analyze all backtest results
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict
import statistics

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/trades_analyzer.log')
    ]
)

logger = logging.getLogger(__name__)


class TradesAnalyzer:
    """
    Analyzes trade patterns to identify what works and what doesn't
    """

    def __init__(self, results_dir: str = "analyzer_results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        
        self.learnings_file = self.results_dir / "trades_analysis.json"
        self.learnings = self._load_learnings()

    def _load_learnings(self) -> Dict:
        """Load previous analysis learnings"""
        if self.learnings_file.exists():
            try:
                with open(self.learnings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load learnings: {e}")
        
        # Initialize structure
        return {
            'winning_patterns': {},
            'losing_patterns': {},
            'hourly_performance': {},
            'volume_patterns': {},
            'rsi_patterns': {},
            'consolidation_patterns': {},
            'parameter_experiments': [],
            'last_updated': None
        }

    def _save_learnings(self):
        """Save learnings to file"""
        self.learnings['last_updated'] = datetime.now().isoformat()
        with open(self.learnings_file, 'w') as f:
            json.dump(self.learnings, f, indent=2)

    def load_backtest_results(self, json_file: str) -> Optional[Dict]:
        """Load backtest results from JSON file"""
        try:
            with open(json_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {json_file}: {e}")
            return None

    def analyze_trades(self, trades: List[Dict]) -> Dict:
        """
        Analyze trades to identify patterns
        
        Args:
            trades: List of trade dicts from backtest
            
        Returns:
            Analysis results dict
        """
        if not trades:
            return {}
        
        analysis = {
            'total_trades': len(trades),
            'wins': [],
            'losses': [],
            'hourly_stats': defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0}),
            'volume_stats': defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0}),
            'rsi_stats': defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0}),
            'duration_stats': {'wins': [], 'losses': []},
            'patterns': {}
        }
        
        for trade in trades:
            # Categorize win/loss
            pnl = trade.get('pnl_dollar', 0) or trade.get('pnl', 0)
            is_win = pnl > 0
            
            if is_win:
                analysis['wins'].append(trade)
            else:
                analysis['losses'].append(trade)
            
            # Hourly performance
            timestamp = trade.get('timestamp') or trade.get('entry_timestamp')
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        dt = timestamp
                    hour = dt.hour
                    analysis['hourly_stats'][hour]['wins' if is_win else 'losses'] += 1
                    analysis['hourly_stats'][hour]['pnl'] += pnl
                except Exception:
                    pass
            
            # Duration stats
            bars_held = trade.get('bars_held', 0)
            if bars_held > 0:
                if is_win:
                    analysis['duration_stats']['wins'].append(bars_held)
                else:
                    analysis['duration_stats']['losses'].append(bars_held)
        
        # Calculate win rates
        analysis['win_rate'] = len(analysis['wins']) / len(trades) if trades else 0
        analysis['total_wins'] = len(analysis['wins'])
        analysis['total_losses'] = len(analysis['losses'])
        
        # Calculate hourly win rates
        for hour, stats in analysis['hourly_stats'].items():
            total = stats['wins'] + stats['losses']
            stats['win_rate'] = stats['wins'] / total if total > 0 else 0
            stats['total_trades'] = total
        
        # Calculate duration averages
        if analysis['duration_stats']['wins']:
            analysis['avg_win_duration'] = statistics.mean(analysis['duration_stats']['wins'])
        if analysis['duration_stats']['losses']:
            analysis['avg_loss_duration'] = statistics.mean(analysis['duration_stats']['losses'])
        
        return analysis

    def identify_patterns(self, analysis: Dict) -> Dict:
        """
        Identify winning and losing patterns
        
        Args:
            analysis: Analysis results from analyze_trades
            
        Returns:
            Patterns dict
        """
        patterns = {
            'winning_patterns': {},
            'losing_patterns': {},
            'insights': []
        }
        
        wins = analysis['wins']
        losses = analysis['losses']
        
        # Best trading hours
        hourly_stats = analysis.get('hourly_stats', {})
        if hourly_stats:
            best_hours = sorted(
                hourly_stats.items(),
                key=lambda x: x[1].get('win_rate', 0),
                reverse=True
            )[:3]
            
            worst_hours = sorted(
                hourly_stats.items(),
                key=lambda x: x[1].get('win_rate', 1.0)
            )[:3]
            
            patterns['winning_patterns']['best_hours'] = [
                {
                    'hour': hour,
                    'win_rate': stats['win_rate'],
                    'total_trades': stats['total_trades'],
                    'total_pnl': stats['pnl']
                }
                for hour, stats in best_hours
            ]
            
            patterns['losing_patterns']['worst_hours'] = [
                {
                    'hour': hour,
                    'win_rate': stats['win_rate'],
                    'total_trades': stats['total_trades'],
                    'total_pnl': stats['pnl']
                }
                for hour, stats in worst_hours
            ]
            
            best_hours_str = ', '.join([f"{h}:00 ({s['win_rate']:.1%})" for h, s in best_hours])
            patterns['insights'].append(f"Best trading hours: {best_hours_str}")
        
        # Duration patterns
        if 'avg_win_duration' in analysis and 'avg_loss_duration' in analysis:
            win_dur = analysis['avg_win_duration']
            loss_dur = analysis['avg_loss_duration']
            
            patterns['winning_patterns']['avg_duration_bars'] = win_dur
            patterns['losing_patterns']['avg_duration_bars'] = loss_dur
            
            if win_dur < loss_dur:
                patterns['insights'].append(
                    f"Wins happen faster ({win_dur:.1f} bars) than losses ({loss_dur:.1f} bars)"
                )
        
        # Volume patterns (if available in trade data)
        # This would require trade data to include volume info
        
        return patterns

    def analyze_backtest_file(self, json_file: str) -> Dict:
        """
        Analyze a single backtest results file
        
        Args:
            json_file: Path to backtest results JSON
            
        Returns:
            Analysis results
        """
        logger.info(f"📊 Analyzing: {json_file}")
        
        results = self.load_backtest_results(json_file)
        if not results:
            return {}
        
        trades = results.get('all_trades', [])
        if not trades:
            logger.warning(f"No trades found in {json_file}")
            return {}
        
        logger.info(f"Found {len(trades)} trades")
        
        # Analyze trades
        analysis = self.analyze_trades(trades)
        
        # Identify patterns
        patterns = self.identify_patterns(analysis)
        
        # Combine results
        full_analysis = {
            'file': json_file,
            'date': datetime.now().isoformat(),
            'summary': {
                'total_trades': analysis['total_trades'],
                'wins': analysis['total_wins'],
                'losses': analysis['total_losses'],
                'win_rate': analysis['win_rate']
            },
            'patterns': patterns,
            'hourly_stats': dict(analysis['hourly_stats'])
        }
        
        # Update learnings
        self._update_learnings(full_analysis)
        
        return full_analysis

    def _update_learnings(self, analysis: Dict):
        """Update learnings database with new analysis"""
        patterns = analysis.get('patterns', {})
        
        # Update winning patterns
        if 'best_hours' in patterns.get('winning_patterns', {}):
            for hour_data in patterns['winning_patterns']['best_hours']:
                hour = hour_data['hour']
                if hour not in self.learnings['hourly_performance']:
                    self.learnings['hourly_performance'][str(hour)] = {
                        'frequency': 0,
                        'win_rate': 0.0,
                        'avg_duration_bars': 0
                    }
                
                # Update with weighted average
                existing = self.learnings['hourly_performance'][str(hour)]
                existing['frequency'] += hour_data['total_trades']
                existing['win_rate'] = (
                    (existing['win_rate'] * (existing['frequency'] - hour_data['total_trades']) +
                     hour_data['win_rate'] * hour_data['total_trades']) / existing['frequency']
                    if existing['frequency'] > 0 else hour_data['win_rate']
                )
        
        # Update duration patterns
        if 'avg_duration_bars' in patterns.get('winning_patterns', {}):
            if 'high_volume_breakout' not in self.learnings['winning_patterns']:
                self.learnings['winning_patterns']['high_volume_breakout'] = {
                    'frequency': 0,
                    'win_rate': 0.0,
                    'avg_duration_bars': 0
                }
            
            pattern = self.learnings['winning_patterns']['high_volume_breakout']
            pattern['frequency'] += analysis['summary']['total_trades']
            pattern['win_rate'] = analysis['summary']['win_rate']
            pattern['avg_duration_bars'] = patterns['winning_patterns'].get('avg_duration_bars', 0)
        
        # Save learnings
        self._save_learnings()

    def analyze_all_backtests(self, reports_dir: str = "backtesting/reports") -> Dict:
        """
        Analyze all backtest result files
        
        Args:
            reports_dir: Directory containing backtest results
            
        Returns:
            Combined analysis
        """
        reports_path = Path(reports_dir)
        if not reports_path.exists():
            logger.error(f"Reports directory not found: {reports_dir}")
            return {}
        
        json_files = list(reports_path.glob("results_*.json"))
        
        if not json_files:
            logger.warning(f"No result files found in {reports_dir}")
            return {}
        
        logger.info(f"Found {len(json_files)} backtest result files")
        
        all_analyses = []
        for json_file in json_files:
            analysis = self.analyze_backtest_file(str(json_file))
            if analysis:
                all_analyses.append(analysis)
        
        # Generate summary report
        summary = self._generate_summary(all_analyses)
        
        return {
            'analyses': all_analyses,
            'summary': summary,
            'learnings': self.learnings
        }

    def _generate_summary(self, analyses: List[Dict]) -> Dict:
        """Generate summary from multiple analyses"""
        total_trades = sum(a['summary']['total_trades'] for a in analyses)
        total_wins = sum(a['summary']['wins'] for a in analyses)
        
        # Aggregate hourly stats
        hourly_aggregate = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total': 0})
        
        for analysis in analyses:
            for hour_str, stats in analysis.get('hourly_stats', {}).items():
                hour = int(hour_str)
                hourly_aggregate[hour]['wins'] += stats.get('wins', 0)
                hourly_aggregate[hour]['losses'] += stats.get('losses', 0)
                hourly_aggregate[hour]['total'] += stats.get('total_trades', 0)
        
        # Calculate best hours
        best_hours = sorted(
            hourly_aggregate.items(),
            key=lambda x: x[1]['wins'] / x[1]['total'] if x[1]['total'] > 0 else 0,
            reverse=True
        )[:5]
        
        return {
            'total_trades': total_trades,
            'total_wins': total_wins,
            'overall_win_rate': total_wins / total_trades if total_trades > 0 else 0,
            'best_hours': [
                {
                    'hour': hour,
                    'win_rate': stats['wins'] / stats['total'] if stats['total'] > 0 else 0,
                    'total_trades': stats['total']
                }
                for hour, stats in best_hours
            ],
            'files_analyzed': len(analyses)
        }

    def print_report(self, analysis: Dict):
        """Print human-readable analysis report"""
        print("\n" + "="*80)
        print("TRADES ANALYSIS REPORT")
        print("="*80)
        
        summary = analysis.get('summary', {})
        print(f"\n📊 SUMMARY:")
        print(f"  Total Trades: {summary.get('total_trades', 0)}")
        print(f"  Wins: {summary.get('wins', 0)}")
        print(f"  Losses: {summary.get('losses', 0)}")
        print(f"  Win Rate: {summary.get('win_rate', 0):.1%}")
        
        patterns = analysis.get('patterns', {})
        if 'winning_patterns' in patterns:
            print(f"\n✅ WINNING PATTERNS:")
            if 'best_hours' in patterns['winning_patterns']:
                print("  Best Trading Hours:")
                for hour_data in patterns['winning_patterns']['best_hours']:
                    print(f"    {hour_data['hour']:02d}:00 - "
                          f"Win Rate: {hour_data['win_rate']:.1%} "
                          f"({hour_data['total_trades']} trades)")
        
        if 'insights' in patterns:
            print(f"\n💡 INSIGHTS:")
            for insight in patterns['insights']:
                print(f"  • {insight}")
        
        print("\n" + "="*80 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Analyze trade patterns from backtest results',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--backtest-file', type=str, help='Path to backtest results JSON')
    parser.add_argument('--analyze-all', action='store_true', help='Analyze all backtest results')
    parser.add_argument('--reports-dir', type=str, default='backtesting/reports',
                       help='Directory with backtest results')
    
    args = parser.parse_args()
    
    analyzer = TradesAnalyzer()
    
    if args.analyze_all:
        result = analyzer.analyze_all_backtests(args.reports_dir)
        if result:
            analyzer.print_report(result['summary'])
            print(f"\n✅ Analysis complete. Learnings saved to {analyzer.learnings_file}")
    elif args.backtest_file:
        analysis = analyzer.analyze_backtest_file(args.backtest_file)
        if analysis:
            analyzer.print_report(analysis)
            print(f"\n✅ Analysis complete. Learnings saved to {analyzer.learnings_file}")
    else:
        parser.error("Must specify --backtest-file or --analyze-all")
    
    sys.exit(0)


if __name__ == '__main__':
    main()
