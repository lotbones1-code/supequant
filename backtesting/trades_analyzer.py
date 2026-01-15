"""
Trades Analyzer
Analyzes winning vs losing trades to identify profitable patterns
Used for continuous strategy improvement
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class TradesAnalyzer:
    """
    Analyzes trade data to find winning patterns
    Tracks: volume strength, RSI levels, time of day, candle patterns
    """

    def __init__(self, trades_csv: str = "backtesting/reports/trades_quick_test.csv"):
        self.trades_csv = Path(trades_csv)
        self.trades = self._load_trades()
        self.analysis = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': []})

    def _load_trades(self) -> List[Dict]:
        """Load trades from CSV"""
        if not self.trades_csv.exists():
            logger.warning(f"Trades CSV not found: {self.trades_csv}")
            return []

        trades = []
        try:
            with open(self.trades_csv) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append(row)
            logger.info(f"📄 Loaded {len(trades)} trades from {self.trades_csv}")
        except Exception as e:
            logger.error(f"Error loading trades: {e}")

        return trades

    def analyze_by_volume(self):
        """
        Analyze win rate by entry volume strength
        Groups trades by volume ratio: weak/medium/strong
        """
        logger.info("\n📊 Analyzing by VOLUME STRENGTH...")

        analysis = {'weak': {'wins': 0, 'losses': 0}, 'medium': {'wins': 0, 'losses': 0}, 'strong': {'wins': 0, 'losses': 0}}

        for trade in self.trades:
            try:
                pnl = float(trade.get('pnl', 0))
                volume_ratio = float(trade.get('volume_ratio', 0))
                is_win = 1 if pnl > 0 else 0

                if volume_ratio < 2.5:
                    category = 'weak'
                elif volume_ratio < 3.5:
                    category = 'medium'
                else:
                    category = 'strong'

                if is_win:
                    analysis[category]['wins'] += 1
                else:
                    analysis[category]['losses'] += 1
            except:
                pass

        # Calculate win rates
        for category in analysis:
            total = analysis[category]['wins'] + analysis[category]['losses']
            if total > 0:
                win_rate = (analysis[category]['wins'] / total) * 100
                logger.info(f"  {category.upper():8} | Wins: {analysis[category]['wins']:2} | "
                           f"Losses: {analysis[category]['losses']:2} | Win Rate: {win_rate:.1f}%")

        return analysis

    def analyze_by_time(self):
        """
        Analyze win rate by time of day
        Some market times are better than others
        """
        logger.info("\n📊 Analyzing by TIME OF DAY...")

        time_analysis = defaultdict(lambda: {'wins': 0, 'losses': 0})

        for trade in self.trades:
            try:
                entry_time = trade.get('entry_time', '')
                if not entry_time:
                    continue

                # Extract hour (assume format: 2026-01-13 02:15)
                hour = int(entry_time.split()[1].split(':')[0])
                pnl = float(trade.get('pnl', 0))
                is_win = 1 if pnl > 0 else 0

                if is_win:
                    time_analysis[hour]['wins'] += 1
                else:
                    time_analysis[hour]['losses'] += 1
            except:
                pass

        # Sort by hour and show
        for hour in sorted(time_analysis.keys()):
            total = time_analysis[hour]['wins'] + time_analysis[hour]['losses']
            if total > 0:
                win_rate = (time_analysis[hour]['wins'] / total) * 100
                logger.info(f"  {hour:02d}:00 | Wins: {time_analysis[hour]['wins']:2} | "
                           f"Losses: {time_analysis[hour]['losses']:2} | Win Rate: {win_rate:.1f}%")

        return dict(time_analysis)

    def analyze_by_duration(self):
        """
        Analyze win rate by how long trade is held
        Short trades vs runners
        """
        logger.info("\n📊 Analyzing by TRADE DURATION...")

        analysis = {'fast': {'wins': 0, 'losses': 0}, 'medium': {'wins': 0, 'losses': 0}, 'slow': {'wins': 0, 'losses': 0}}

        for trade in self.trades:
            try:
                bars_held = int(trade.get('bars_held', 0))
                pnl = float(trade.get('pnl', 0))
                is_win = 1 if pnl > 0 else 0

                if bars_held <= 3:
                    category = 'fast'
                elif bars_held <= 10:
                    category = 'medium'
                else:
                    category = 'slow'

                if is_win:
                    analysis[category]['wins'] += 1
                else:
                    analysis[category]['losses'] += 1
            except:
                pass

        for category in analysis:
            total = analysis[category]['wins'] + analysis[category]['losses']
            if total > 0:
                win_rate = (analysis[category]['wins'] / total) * 100
                logger.info(f"  {category.upper():8} | Wins: {analysis[category]['wins']:2} | "
                           f"Losses: {analysis[category]['losses']:2} | Win Rate: {win_rate:.1f}%")

        return analysis

    def analyze_patterns(self):
        """
        Find correlations between entry conditions and outcomes
        E.g., "high volume + RSI 50+ = 65% win rate"
        """
        logger.info("\n📊 Analyzing PATTERN CORRELATIONS...")

        patterns = {
            'high_vol_high_rsi': {'wins': 0, 'losses': 0},
            'high_vol_low_rsi': {'wins': 0, 'losses': 0},
            'low_vol_high_rsi': {'wins': 0, 'losses': 0},
            'low_vol_low_rsi': {'wins': 0, 'losses': 0},
        }

        for trade in self.trades:
            try:
                volume_ratio = float(trade.get('volume_ratio', 0))
                rsi = float(trade.get('rsi_at_entry', 50))
                pnl = float(trade.get('pnl', 0))
                is_win = 1 if pnl > 0 else 0

                vol_category = 'high_vol' if volume_ratio > 3.0 else 'low_vol'
                rsi_category = 'high_rsi' if rsi > 55 else 'low_rsi'
                pattern = f"{vol_category}_{rsi_category}"

                if is_win:
                    patterns[pattern]['wins'] += 1
                else:
                    patterns[pattern]['losses'] += 1
            except:
                pass

        for pattern in patterns:
            total = patterns[pattern]['wins'] + patterns[pattern]['losses']
            if total > 0:
                win_rate = (patterns[pattern]['wins'] / total) * 100
                logger.info(f"  {pattern:20} | Wins: {patterns[pattern]['wins']:2} | "
                           f"Losses: {patterns[pattern]['losses']:2} | Win Rate: {win_rate:.1f}%")

        return patterns

    def identify_worst_setups(self, threshold: float = 0.3):
        """
        Identify setups with win rate below threshold
        These should be filtered out
        """
        logger.info(f"\n📈 WORST SETUPS (Win Rate < {threshold*100:.0f}%)...")

        bad_patterns = []

        # Check volume levels
        volume_analysis = self.analyze_by_volume()
        for vol_type, stats in volume_analysis.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                win_rate = stats['wins'] / total
                if win_rate < threshold:
                    bad_patterns.append({
                        'type': f'volume_{vol_type}',
                        'win_rate': win_rate,
                        'action': 'FILTER OUT'
                    })
                    logger.info(f"  ❌ {vol_type.upper()} volume setups: {win_rate*100:.1f}% win rate - FILTER OUT")

        # Check times
        time_analysis = self.analyze_by_time()
        for hour, stats in time_analysis.items():
            total = stats['wins'] + stats['losses']
            if total > 2:  # Only if enough samples
                win_rate = stats['wins'] / total
                if win_rate < threshold:
                    bad_patterns.append({
                        'type': f'time_{hour:02d}',
                        'win_rate': win_rate,
                        'action': 'FILTER OUT',
                    })
                    logger.info(f"  ❌ {hour:02d}:00 trades: {win_rate*100:.1f}% win rate - FILTER OUT")

        return bad_patterns

    def identify_best_setups(self, threshold: float = 0.55):
        """
        Identify best-performing setups
        These should be doubled down on
        """
        logger.info(f"\n✨ BEST SETUPS (Win Rate > {threshold*100:.0f}%)...")

        good_patterns = []

        # Check volume levels
        volume_analysis = self.analyze_by_volume()
        for vol_type, stats in volume_analysis.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                win_rate = stats['wins'] / total
                if win_rate > threshold:
                    good_patterns.append({
                        'type': f'volume_{vol_type}',
                        'win_rate': win_rate,
                        'action': 'SCALE UP',
                        'trades': total,
                    })
                    logger.info(f"  ✅ {vol_type.upper()} volume setups: {win_rate*100:.1f}% win rate - SCALE UP")

        # Check times
        time_analysis = self.analyze_by_time()
        for hour, stats in time_analysis.items():
            total = stats['wins'] + stats['losses']
            if total > 2:  # Only if enough samples
                win_rate = stats['wins'] / total
                if win_rate > threshold:
                    good_patterns.append({
                        'type': f'time_{hour:02d}',
                        'win_rate': win_rate,
                        'action': 'SCALE UP',
                        'trades': total,
                    })
                    logger.info(f"  ✅ {hour:02d}:00 trades: {win_rate*100:.1f}% win rate ({total} trades) - SCALE UP")

        return good_patterns

    def generate_filter_rules(self) -> Dict:
        """
        Generate recommended filter rules based on analysis
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"📈 RECOMMENDED FILTER RULES")
        logger.info(f"{'='*60}")

        rules = {
            'volume_filters': [],
            'time_filters': [],
            'pattern_filters': [],
        }

        # Volume filters
        volume_analysis = self.analyze_by_volume()
        for vol_type, stats in volume_analysis.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                win_rate = stats['wins'] / total
                if vol_type == 'weak' and win_rate < 0.35:
                    rules['volume_filters'].append('Skip trades with volume_ratio < 2.5')
                    logger.info(f"\n📋 RULE: Skip trades with volume_ratio < 2.5 ({win_rate*100:.1f}% win rate)")

        # Time filters
        time_analysis = self.analyze_by_time()
        for hour in sorted(time_analysis.keys()):
            stats = time_analysis[hour]
            total = stats['wins'] + stats['losses']
            if total > 2:
                win_rate = stats['wins'] / total
                if win_rate < 0.25:
                    rules['time_filters'].append(f'Skip trades during {hour:02d}:00 UTC')
                    logger.info(f"\n📋 RULE: Skip trades during {hour:02d}:00 UTC ({win_rate*100:.1f}% win rate)")

        return rules

    def run_full_analysis(self):
        """
        Run complete trade analysis
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 TRADES ANALYZER - FULL REPORT")
        logger.info(f"{'='*60}")

        # Run all analyses
        self.analyze_by_volume()
        self.analyze_by_time()
        self.analyze_by_duration()
        self.analyze_patterns()

        # Identify patterns
        worst = self.identify_worst_setups()
        best = self.identify_best_setups()

        # Generate rules
        rules = self.generate_filter_rules()

        logger.info(f"\n{'='*60}")
        logger.info(f"🌟 SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total trades analyzed: {len(self.trades)}")
        logger.info(f"Worst setups found: {len(worst)}")
        logger.info(f"Best setups found: {len(best)}")
        logger.info(f"Filter rules recommended: {sum(len(v) for v in rules.values())}")

        # Save results
        self._save_analysis({
            'worst_setups': worst,
            'best_setups': best,
            'filter_rules': rules,
            'total_trades': len(self.trades),
        })

    def _save_analysis(self, analysis: Dict):
        """
        Save analysis results to file
        """
        output_file = Path("backtesting/trades_analysis.json")
        with open(output_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        logger.info(f"\n💾 Analysis saved to {output_file}")


if __name__ == "__main__":
    analyzer = TradesAnalyzer()
    analyzer.run_full_analysis()
