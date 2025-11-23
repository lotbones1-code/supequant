"""
Report Generator
Creates comprehensive backtest reports in multiple formats

Generates:
- Summary reports (text)
- Trade-by-trade CSV exports
- Filter analysis
- Performance visualizations (text-based)
- Recommendations based on results
"""

import json
import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generate comprehensive backtest reports

    Creates multiple output formats for analysis
    """

    def __init__(self, output_dir: str = "backtesting/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📄 ReportGenerator initialized (output: {output_dir})")

    def generate_full_report(self, results: Dict, metrics: Dict,
                            run_name: Optional[str] = None) -> str:
        """
        Generate comprehensive report with all analyses

        Returns:
            Path to generated report
        """
        if run_name is None:
            run_name = datetime.now().strftime('%Y%m%d_%H%M%S')

        report_file = self.output_dir / f"backtest_report_{run_name}.txt"

        logger.info(f"📝 Generating full report: {report_file}")

        with open(report_file, 'w') as f:
            # Header
            f.write("="*80 + "\n")
            f.write("BACKTEST FULL REPORT\n")
            f.write("="*80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Run Name: {run_name}\n")
            f.write("="*80 + "\n\n")

            # Executive Summary
            f.write(self._format_executive_summary(results, metrics))

            # Detailed Performance
            f.write(self._format_performance_details(metrics))

            # Filter Analysis
            f.write(self._format_filter_analysis(results))

            # Trade Analysis
            f.write(self._format_trade_analysis(results['all_trades']))

            # Recommendations
            f.write(self._format_recommendations(results, metrics))

            # Footer
            f.write("\n" + "="*80 + "\n")
            f.write("END OF REPORT\n")
            f.write("="*80 + "\n")

        logger.info(f"✅ Report generated: {report_file}")
        return str(report_file)

    def export_trades_csv(self, trades: List, run_name: Optional[str] = None) -> str:
        """
        Export all trades to CSV for detailed analysis

        Args:
            trades: List of BacktestTrade objects
            run_name: Optional name for the run

        Returns:
            Path to CSV file
        """
        if run_name is None:
            run_name = datetime.now().strftime('%Y%m%d_%H%M%S')

        csv_file = self.output_dir / f"trades_{run_name}.csv"

        executed_trades = [t for t in trades if t.executed]

        if not executed_trades:
            logger.warning("⚠️  No executed trades to export")
            return ""

        logger.info(f"📊 Exporting {len(executed_trades)} trades to CSV: {csv_file}")

        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'signal_id', 'timestamp', 'direction', 'strategy',
                'entry_price', 'stop_price', 'target_price',
                'actual_entry', 'exit_price', 'exit_reason',
                'bars_held', 'pnl_dollar', 'pnl_percent',
                'win', 'mfe', 'mae', 'rr_achieved',
                'filter_passed', 'failed_filters'
            ])

            # Data rows
            for trade in executed_trades:
                writer.writerow([
                    trade.signal_id,
                    trade.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    trade.direction,
                    trade.strategy,
                    round(trade.entry_price, 2),
                    round(trade.stop_price, 2),
                    round(trade.target_price, 2),
                    round(trade.actual_entry_price, 2),
                    round(trade.exit_price, 2) if trade.exit_price else '',
                    trade.exit_reason or '',
                    trade.bars_held,
                    round(trade.pnl_dollar, 2),
                    round(trade.pnl_percent * 100, 2),
                    trade.win,
                    round(trade.max_favorable_excursion * 100, 2),
                    round(trade.max_adverse_excursion * 100, 2),
                    round(trade.risk_reward_achieved, 2),
                    trade.filter_passed,
                    ','.join(trade.filter_results.get('failed_filters', []))
                ])

        logger.info(f"✅ CSV exported: {csv_file}")
        return str(csv_file)

    def export_json(self, results: Dict, metrics: Dict, run_name: Optional[str] = None) -> str:
        """
        Export results to JSON for programmatic access

        Args:
            results: Backtest results
            metrics: Performance metrics
            run_name: Optional name for the run

        Returns:
            Path to JSON file
        """
        if run_name is None:
            run_name = datetime.now().strftime('%Y%m%d_%H%M%S')

        json_file = self.output_dir / f"results_{run_name}.json"

        logger.info(f"💾 Exporting results to JSON: {json_file}")

        # Remove trades from results (too large for JSON)
        results_copy = results.copy()
        results_copy.pop('all_trades', None)

        output = {
            'run_name': run_name,
            'generated': datetime.now().isoformat(),
            'results': results_copy,
            'metrics': metrics
        }

        with open(json_file, 'w') as f:
            json.dump(output, f, indent=2, default=str)

        logger.info(f"✅ JSON exported: {json_file}")
        return str(json_file)

    def _format_executive_summary(self, results: Dict, metrics: Dict) -> str:
        """Format executive summary"""
        lines = []
        lines.append("\n" + "="*80)
        lines.append("EXECUTIVE SUMMARY")
        lines.append("="*80 + "\n")

        summary = results['summary']
        trades = results['trades']
        signals = results['signals']

        # Capital & Returns
        lines.append("💰 CAPITAL & RETURNS:")
        lines.append(f"  Initial Capital: ${summary['initial_capital']:,.2f}")
        lines.append(f"  Final Capital: ${summary['final_capital']:,.2f}")
        lines.append(f"  Total PnL: ${summary['total_pnl']:+,.2f}")
        lines.append(f"  Total Return: {summary['total_return_pct']:+.2f}%")
        if 'returns' in metrics:
            lines.append(f"  CAGR: {metrics['returns'].get('cagr', 0):.2f}%")
        lines.append(f"  Max Drawdown: {summary['max_drawdown_pct']:.2f}%")

        # Trade Performance
        lines.append("\n📈 TRADE PERFORMANCE:")
        lines.append(f"  Total Signals: {signals['total_signals']}")
        lines.append(f"  Signals Passed Filters: {signals['signals_passed_filters']} ({signals['filter_pass_rate']:.1f}%)")
        lines.append(f"  Trades Executed: {trades['total_trades']}")
        lines.append(f"  Wins: {trades['wins']} | Losses: {trades['losses']} | BE: {trades['breakevens']}")
        lines.append(f"  Win Rate: {trades['win_rate']:.2f}%")

        # Risk Metrics
        if 'risk' in metrics:
            risk = metrics['risk']
            lines.append("\n⚠️  RISK METRICS:")
            lines.append(f"  Sharpe Ratio: {risk.get('sharpe_ratio', 0):.2f}")
            lines.append(f"  Profit Factor: {metrics['trade_stats'].get('profit_factor', 0):.2f}")
            lines.append(f"  Expectancy: ${metrics['trade_stats'].get('expectancy_dollar', 0):.2f}/trade")

        # Overall Assessment
        lines.append("\n🎯 ASSESSMENT:")
        assessment = self._assess_performance(results, metrics)
        lines.append(f"  {assessment}")

        lines.append("\n")
        return "\n".join(lines)

    def _format_performance_details(self, metrics: Dict) -> str:
        """Format detailed performance metrics"""
        from .performance_metrics import PerformanceMetrics
        return PerformanceMetrics.format_metrics_report(metrics)

    def _format_filter_analysis(self, results: Dict) -> str:
        """Format filter rejection analysis"""
        lines = []
        lines.append("\n" + "="*80)
        lines.append("FILTER ANALYSIS")
        lines.append("="*80 + "\n")

        signals = results['signals']
        rejections = results['filter_rejections']

        lines.append("📊 FILTER REJECTION BREAKDOWN:\n")

        total_rejected = signals['signals_rejected']
        if total_rejected == 0:
            lines.append("  ✅ All signals passed filters (no rejections)\n")
            return "\n".join(lines)

        # Sort by rejection count
        sorted_filters = sorted(rejections.items(), key=lambda x: x[1], reverse=True)

        for filter_name, count in sorted_filters:
            pct = (count / total_rejected * 100) if total_rejected > 0 else 0
            lines.append(f"  {filter_name}: {count} rejections ({pct:.1f}%)")

        # Insights
        lines.append("\n🔍 FILTER INSIGHTS:")

        if sorted_filters:
            top_filter = sorted_filters[0][0]
            top_count = sorted_filters[0][1]
            lines.append(f"  • Most restrictive filter: {top_filter} ({top_count} rejections)")

        filter_pass_rate = signals['filter_pass_rate']
        if filter_pass_rate < 10:
            lines.append("  ⚠️  WARNING: Very low filter pass rate (<10%)")
            lines.append("     Consider loosening filter thresholds")
        elif filter_pass_rate > 50:
            lines.append("  ⚠️  WARNING: High filter pass rate (>50%)")
            lines.append("     Filters may not be selective enough")
        else:
            lines.append(f"  ✅ Filter pass rate ({filter_pass_rate:.1f}%) is reasonable")

        lines.append("\n")
        return "\n".join(lines)

    def _format_trade_analysis(self, trades: List) -> str:
        """Format trade-by-trade analysis"""
        lines = []
        lines.append("\n" + "="*80)
        lines.append("TRADE ANALYSIS")
        lines.append("="*80 + "\n")

        executed_trades = [t for t in trades if t.executed]

        if not executed_trades:
            lines.append("  No trades executed\n")
            return "\n".join(lines)

        # Strategy breakdown
        strategy_stats = {}
        for trade in executed_trades:
            if trade.strategy not in strategy_stats:
                strategy_stats[trade.strategy] = {'total': 0, 'wins': 0, 'pnl': 0}
            strategy_stats[trade.strategy]['total'] += 1
            if trade.win:
                strategy_stats[trade.strategy]['wins'] += 1
            strategy_stats[trade.strategy]['pnl'] += trade.pnl_dollar

        lines.append("📊 PERFORMANCE BY STRATEGY:\n")
        for strategy, stats in strategy_stats.items():
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            lines.append(f"  {strategy.upper()}:")
            lines.append(f"    Trades: {stats['total']}")
            lines.append(f"    Wins: {stats['wins']} ({win_rate:.1f}%)")
            lines.append(f"    PnL: ${stats['pnl']:+,.2f}\n")

        # Direction breakdown
        long_trades = [t for t in executed_trades if t.direction == 'long']
        short_trades = [t for t in executed_trades if t.direction == 'short']

        lines.append("📊 PERFORMANCE BY DIRECTION:\n")

        if long_trades:
            long_wins = sum(1 for t in long_trades if t.win)
            long_pnl = sum(t.pnl_dollar for t in long_trades)
            long_wr = (long_wins / len(long_trades) * 100)
            lines.append(f"  LONG:")
            lines.append(f"    Trades: {len(long_trades)}")
            lines.append(f"    Wins: {long_wins} ({long_wr:.1f}%)")
            lines.append(f"    PnL: ${long_pnl:+,.2f}\n")

        if short_trades:
            short_wins = sum(1 for t in short_trades if t.win)
            short_pnl = sum(t.pnl_dollar for t in short_trades)
            short_wr = (short_wins / len(short_trades) * 100)
            lines.append(f"  SHORT:")
            lines.append(f"    Trades: {len(short_trades)}")
            lines.append(f"    Wins: {short_wins} ({short_wr:.1f}%)")
            lines.append(f"    PnL: ${short_pnl:+,.2f}\n")

        lines.append("\n")
        return "\n".join(lines)

    def _format_recommendations(self, results: Dict, metrics: Dict) -> str:
        """Generate actionable recommendations"""
        lines = []
        lines.append("\n" + "="*80)
        lines.append("RECOMMENDATIONS")
        lines.append("="*80 + "\n")

        recommendations = []

        # Analyze results and provide recommendations
        signals = results['signals']
        trades = results['trades']
        summary = results['summary']

        # Filter pass rate
        filter_pass_rate = signals['filter_pass_rate']
        if filter_pass_rate < 10:
            recommendations.append("🔧 FILTER TUNING: Pass rate is very low (<10%). Consider:")
            recommendations.append("   - Loosening threshold requirements")
            recommendations.append("   - Disabling overly restrictive filters")
            recommendations.append("   - Reviewing filter logic for false rejections")

        # Win rate
        win_rate = trades['win_rate']
        if win_rate < 40:
            recommendations.append("📉 LOW WIN RATE: Win rate is below 40%. Consider:")
            recommendations.append("   - Reviewing entry criteria")
            recommendations.append("   - Adjusting stop loss placement")
            recommendations.append("   - Checking if market conditions suit strategies")
        elif win_rate > 70:
            recommendations.append("⚠️  SUSPICIOUSLY HIGH WIN RATE: >70% may indicate:")
            recommendations.append("   - Overfitting to historical data")
            recommendations.append("   - Stops too wide (cutting winners too early)")
            recommendations.append("   - Need for out-of-sample testing")

        # Profit factor
        if 'trade_stats' in metrics:
            pf = metrics['trade_stats'].get('profit_factor', 0)
            if pf < 1.0:
                recommendations.append("❌ NEGATIVE EXPECTANCY: Profit factor < 1.0")
                recommendations.append("   - System is losing money")
                recommendations.append("   - DO NOT trade this live")
                recommendations.append("   - Major strategy revision needed")
            elif pf < 1.5:
                recommendations.append("⚠️  LOW PROFIT FACTOR: PF < 1.5 is marginal")
                recommendations.append("   - Account for commissions and slippage")
                recommendations.append("   - May not be profitable after costs")

        # Max drawdown
        max_dd = summary['max_drawdown_pct']
        if max_dd > 20:
            recommendations.append("⚠️  HIGH DRAWDOWN: Max DD > 20%")
            recommendations.append("   - Reduce position size")
            recommendations.append("   - Implement stricter daily loss limits")
            recommendations.append("   - Consider risk per trade < 0.5%")

        # Trade count
        total_trades = trades['total_trades']
        if total_trades < 30:
            recommendations.append("⚠️  INSUFFICIENT SAMPLE SIZE: < 30 trades")
            recommendations.append("   - Results may not be statistically significant")
            recommendations.append("   - Test on longer time period")
            recommendations.append("   - Minimum 100 trades recommended for validation")

        # Sharpe ratio
        if 'risk' in metrics:
            sharpe = metrics['risk'].get('sharpe_ratio', 0)
            if sharpe < 1.0:
                recommendations.append("📊 LOW RISK-ADJUSTED RETURNS: Sharpe < 1.0")
                recommendations.append("   - Returns not adequate for risk taken")
                recommendations.append("   - Consider less risky instruments")
            elif sharpe > 2.0:
                recommendations.append("✅ EXCELLENT RISK-ADJUSTED RETURNS: Sharpe > 2.0")
                recommendations.append("   - Strong risk/return profile")
                recommendations.append("   - Verify results with forward testing")

        # If profitable
        if summary['total_pnl'] > 0 and total_trades >= 30:
            recommendations.append("\n✅ SYSTEM SHOWS PROMISE:")
            recommendations.append("   Next steps:")
            recommendations.append("   1. Run on different time periods (walk-forward)")
            recommendations.append("   2. Test on different market conditions")
            recommendations.append("   3. Paper trade for 30-90 days")
            recommendations.append("   4. Start live with reduced size (0.25% risk)")

        if not recommendations:
            recommendations.append("✅ No major issues detected")
            recommendations.append("   Continue with standard validation process")

        for rec in recommendations:
            lines.append(rec)

        lines.append("\n")
        return "\n".join(lines)

    def _assess_performance(self, results: Dict, metrics: Dict) -> str:
        """Overall performance assessment"""
        summary = results['summary']
        trades = results['trades']

        total_pnl = summary['total_pnl']
        win_rate = trades['win_rate']
        total_trades = trades['total_trades']

        if total_trades < 30:
            return "⚠️  Insufficient data (< 30 trades) - Results inconclusive"

        if total_pnl <= 0:
            return "❌ LOSING SYSTEM - Do not trade live"

        if 'trade_stats' in metrics:
            pf = metrics['trade_stats'].get('profit_factor', 0)
            if pf < 1.5:
                return "⚠️  MARGINAL SYSTEM - May not be profitable after costs"

        if 'risk' in metrics:
            sharpe = metrics['risk'].get('sharpe_ratio', 0)
            if sharpe > 2.0 and win_rate > 50:
                return "✅ EXCELLENT SYSTEM - Strong candidate for live trading (after validation)"
            elif sharpe > 1.0:
                return "✅ GOOD SYSTEM - Shows promise, continue validation"

        return "⚠️  NEEDS IMPROVEMENT - Review recommendations below"
