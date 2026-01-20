"""
Performance Metrics Calculator
Calculates professional-grade trading performance metrics

Provides comprehensive analysis including:
- Return metrics (total return, CAGR, monthly returns)
- Risk metrics (Sharpe, Sortino, max drawdown, volatility)
- Trade statistics (win rate, profit factor, expectancy)
- Risk/Reward analysis
- Consistency metrics
"""

import logging
from typing import List, Dict
from datetime import datetime
import math

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """
    Calculate comprehensive trading performance metrics

    Professional metrics used by hedge funds and prop traders
    """

    @staticmethod
    def calculate_all(backtest_results: Dict, trades: List) -> Dict:
        """
        Calculate all performance metrics

        Args:
            backtest_results: Results dict from backtesting engine
            trades: List of BacktestTrade objects

        Returns:
            Dict with comprehensive metrics
        """
        executed_trades = [t for t in trades if t.executed]

        if not executed_trades:
            logger.warning("⚠️  No executed trades to analyze")
            return {}

        wins = [t for t in executed_trades if t.win]
        losses = [t for t in executed_trades if not t.win and t.pnl_dollar < 0]

        metrics = {}

        # Basic metrics
        metrics['returns'] = PerformanceMetrics._calculate_returns(backtest_results, executed_trades)

        # Risk metrics
        metrics['risk'] = PerformanceMetrics._calculate_risk_metrics(backtest_results, executed_trades)

        # Trade statistics
        metrics['trade_stats'] = PerformanceMetrics._calculate_trade_stats(executed_trades, wins, losses)

        # Risk/Reward
        metrics['risk_reward'] = PerformanceMetrics._calculate_risk_reward(executed_trades)

        # Consistency
        metrics['consistency'] = PerformanceMetrics._calculate_consistency(executed_trades)

        # Time analysis
        metrics['time_analysis'] = PerformanceMetrics._calculate_time_analysis(executed_trades)

        return metrics

    @staticmethod
    def _calculate_returns(results: Dict, trades: List) -> Dict:
        """Calculate return metrics"""
        summary = results['summary']

        initial = summary['initial_capital']
        final = summary['final_capital']
        total_return = (final - initial) / initial

        # Calculate CAGR if we have time period
        if trades:
            first_trade = min(trades, key=lambda t: t.timestamp)
            last_trade = max(trades, key=lambda t: t.timestamp)
            days = (last_trade.timestamp - first_trade.timestamp).days
            years = days / 365.0 if days > 0 else 1.0

            cagr = (pow(final / initial, 1 / years) - 1) * 100 if years > 0 else 0
        else:
            cagr = 0
            years = 0

        return {
            'total_return_pct': total_return * 100,
            'total_return_dollar': final - initial,
            'cagr': cagr,
            'days_traded': days if trades else 0,
            'years': round(years, 2)
        }

    @staticmethod
    def _calculate_risk_metrics(results: Dict, trades: List) -> Dict:
        """Calculate risk-adjusted metrics"""
        if not trades:
            return {}

        returns = [t.pnl_percent for t in trades]

        # Volatility (standard deviation of returns)
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = math.sqrt(variance) * 100  # Convert to percentage

        # Sharpe Ratio (assume 0% risk-free rate)
        # Annualize: Sharpe * sqrt(252 trading days)
        if volatility > 0:
            sharpe = (mean_return / (volatility / 100)) * math.sqrt(252)
        else:
            sharpe = 0

        # Sortino Ratio (only downside deviation)
        negative_returns = [r for r in returns if r < 0]
        if negative_returns:
            downside_variance = sum(r ** 2 for r in negative_returns) / len(negative_returns)
            downside_deviation = math.sqrt(downside_variance) * 100
            if downside_deviation > 0:
                sortino = (mean_return / (downside_deviation / 100)) * math.sqrt(252)
            else:
                sortino = 0
        else:
            sortino = 0

        # Max Drawdown
        max_dd = results['summary']['max_drawdown_pct']

        # Calmar Ratio (CAGR / Max Drawdown)
        returns_metrics = PerformanceMetrics._calculate_returns(results, trades)
        cagr = returns_metrics['cagr']
        calmar = cagr / max_dd if max_dd > 0 else 0

        return {
            'volatility_pct': round(volatility, 2),
            'sharpe_ratio': round(sharpe, 2),
            'sortino_ratio': round(sortino, 2),
            'max_drawdown_pct': round(max_dd, 2),
            'calmar_ratio': round(calmar, 2)
        }

    @staticmethod
    def _calculate_trade_stats(trades: List, wins: List, losses: List) -> Dict:
        """Calculate trade statistics"""
        total_trades = len(trades)
        num_wins = len(wins)
        num_losses = len(losses)
        breakevens = total_trades - num_wins - num_losses

        # Win rate
        win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0

        # Average win/loss
        avg_win = sum(t.pnl_dollar for t in wins) / num_wins if num_wins > 0 else 0
        avg_loss = sum(t.pnl_dollar for t in losses) / num_losses if num_losses > 0 else 0

        # Profit factor
        gross_profit = sum(t.pnl_dollar for t in wins)
        gross_loss = abs(sum(t.pnl_dollar for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Expectancy (average $ per trade)
        total_pnl = sum(t.pnl_dollar for t in trades)
        expectancy = total_pnl / total_trades if total_trades > 0 else 0

        # Kelly Criterion
        # Kelly = W - [(1-W)/R] where W=win_rate, R=avg_win/avg_loss
        if num_wins > 0 and num_losses > 0 and avg_loss != 0:
            win_rate_decimal = win_rate / 100
            rr_ratio = abs(avg_win / avg_loss)
            kelly = win_rate_decimal - ((1 - win_rate_decimal) / rr_ratio)
            kelly_pct = kelly * 100
        else:
            kelly_pct = 0

        # Largest win/loss
        largest_win = max((t.pnl_dollar for t in wins), default=0)
        largest_loss = min((t.pnl_dollar for t in losses), default=0)

        # Win/loss streaks
        streak_wins, streak_losses = PerformanceMetrics._calculate_streaks(trades)

        return {
            'total_trades': total_trades,
            'wins': num_wins,
            'losses': num_losses,
            'breakevens': breakevens,
            'win_rate_pct': round(win_rate, 2),
            'avg_win_dollar': round(avg_win, 2),
            'avg_loss_dollar': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'expectancy_dollar': round(expectancy, 2),
            'kelly_pct': round(kelly_pct, 2),
            'largest_win': round(largest_win, 2),
            'largest_loss': round(largest_loss, 2),
            'max_consecutive_wins': streak_wins,
            'max_consecutive_losses': streak_losses
        }

    @staticmethod
    def _calculate_risk_reward(trades: List) -> Dict:
        """Calculate risk/reward metrics"""
        if not trades:
            return {}

        # Average R:R achieved
        rr_ratios = [t.risk_reward_achieved for t in trades if t.risk_reward_achieved > 0]
        avg_rr = sum(rr_ratios) / len(rr_ratios) if rr_ratios else 0

        # MFE/MAE analysis
        mfe_values = [t.max_favorable_excursion for t in trades]
        mae_values = [t.max_adverse_excursion for t in trades]

        avg_mfe = sum(mfe_values) / len(mfe_values) if mfe_values else 0
        avg_mae = sum(mae_values) / len(mae_values) if mae_values else 0

        # MFE/MAE ratio (higher is better - means we capture more of favorable moves)
        mfe_mae_ratio = avg_mfe / avg_mae if avg_mae > 0 else 0

        return {
            'avg_risk_reward': round(avg_rr, 2),
            'avg_mfe_pct': round(avg_mfe * 100, 2),
            'avg_mae_pct': round(avg_mae * 100, 2),
            'mfe_mae_ratio': round(mfe_mae_ratio, 2)
        }

    @staticmethod
    def _calculate_consistency(trades: List) -> Dict:
        """Calculate consistency metrics"""
        if not trades:
            return {}

        # Group trades by day
        daily_pnl = {}
        for trade in trades:
            day = trade.timestamp.strftime('%Y-%m-%d')
            daily_pnl[day] = daily_pnl.get(day, 0) + trade.pnl_dollar

        # Winning days vs losing days
        winning_days = sum(1 for pnl in daily_pnl.values() if pnl > 0)
        losing_days = sum(1 for pnl in daily_pnl.values() if pnl < 0)
        total_days = len(daily_pnl)

        daily_win_rate = (winning_days / total_days * 100) if total_days > 0 else 0

        # Average daily PnL
        avg_daily_pnl = sum(daily_pnl.values()) / total_days if total_days > 0 else 0

        # Best/Worst day
        best_day = max(daily_pnl.values()) if daily_pnl else 0
        worst_day = min(daily_pnl.values()) if daily_pnl else 0

        return {
            'total_trading_days': total_days,
            'winning_days': winning_days,
            'losing_days': losing_days,
            'daily_win_rate_pct': round(daily_win_rate, 2),
            'avg_daily_pnl': round(avg_daily_pnl, 2),
            'best_day': round(best_day, 2),
            'worst_day': round(worst_day, 2)
        }

    @staticmethod
    def _calculate_time_analysis(trades: List) -> Dict:
        """Analyze time-based patterns"""
        if not trades:
            return {}

        # Average trade duration
        durations = [t.bars_held for t in trades]
        avg_duration = sum(durations) / len(durations) if durations else 0

        # Duration for wins vs losses
        wins = [t for t in trades if t.win]
        losses = [t for t in trades if not t.win and t.pnl_dollar < 0]

        avg_win_duration = sum(t.bars_held for t in wins) / len(wins) if wins else 0
        avg_loss_duration = sum(t.bars_held for t in losses) / len(losses) if losses else 0

        # Exit reasons distribution
        exit_reasons = {}
        for trade in trades:
            reason = trade.exit_reason or 'unknown'
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        return {
            'avg_trade_duration_bars': round(avg_duration, 1),
            'avg_win_duration_bars': round(avg_win_duration, 1),
            'avg_loss_duration_bars': round(avg_loss_duration, 1),
            'exit_reasons': exit_reasons
        }

    @staticmethod
    def _calculate_streaks(trades: List) -> tuple:
        """Calculate max consecutive wins and losses"""
        if not trades:
            return 0, 0

        current_win_streak = 0
        current_loss_streak = 0
        max_win_streak = 0
        max_loss_streak = 0

        for trade in trades:
            if trade.win:
                current_win_streak += 1
                current_loss_streak = 0
                max_win_streak = max(max_win_streak, current_win_streak)
            elif trade.pnl_dollar < 0:
                current_loss_streak += 1
                current_win_streak = 0
                max_loss_streak = max(max_loss_streak, current_loss_streak)
            else:
                # Breakeven
                current_win_streak = 0
                current_loss_streak = 0

        return max_win_streak, max_loss_streak

    @staticmethod
    def format_metrics_report(metrics: Dict) -> str:
        """
        Format metrics into a readable report
        """
        if not metrics:
            return "No metrics available"

        lines = []
        lines.append("\n" + "="*60)
        lines.append("PERFORMANCE METRICS REPORT")
        lines.append("="*60)

        # Returns
        if 'returns' in metrics:
            r = metrics['returns']
            lines.append("\n📈 RETURNS:")
            lines.append(f"  Total Return: ${r.get('total_return_dollar', 0):+,.2f} ({r.get('total_return_pct', 0):+.2f}%)")
            lines.append(f"  CAGR: {r.get('cagr', 0):.2f}%")
            lines.append(f"  Period: {r.get('days_traded', 0)} days ({r.get('years', 0):.2f} years)")

        # Risk
        if 'risk' in metrics:
            r = metrics['risk']
            lines.append("\n⚠️  RISK METRICS:")
            lines.append(f"  Sharpe Ratio: {r.get('sharpe_ratio', 0):.2f}")
            lines.append(f"  Sortino Ratio: {r.get('sortino_ratio', 0):.2f}")
            lines.append(f"  Max Drawdown: {r.get('max_drawdown_pct', 0):.2f}%")
            lines.append(f"  Volatility: {r.get('volatility_pct', 0):.2f}%")
            lines.append(f"  Calmar Ratio: {r.get('calmar_ratio', 0):.2f}")

        # Trade Stats
        if 'trade_stats' in metrics:
            t = metrics['trade_stats']
            lines.append("\n📊 TRADE STATISTICS:")
            lines.append(f"  Total Trades: {t.get('total_trades', 0)}")
            lines.append(f"  Wins: {t.get('wins', 0)} | Losses: {t.get('losses', 0)} | BE: {t.get('breakevens', 0)}")
            lines.append(f"  Win Rate: {t.get('win_rate_pct', 0):.2f}%")
            lines.append(f"  Profit Factor: {t.get('profit_factor', 0):.2f}")
            lines.append(f"  Expectancy: ${t.get('expectancy_dollar', 0):.2f} per trade")
            lines.append(f"  Kelly %: {t.get('kelly_pct', 0):.2f}%")
            lines.append(f"  Avg Win: ${t.get('avg_win_dollar', 0):.2f}")
            lines.append(f"  Avg Loss: ${t.get('avg_loss_dollar', 0):.2f}")
            lines.append(f"  Largest Win: ${t.get('largest_win', 0):.2f}")
            lines.append(f"  Largest Loss: ${t.get('largest_loss', 0):.2f}")
            lines.append(f"  Max Win Streak: {t.get('max_consecutive_wins', 0)}")
            lines.append(f"  Max Loss Streak: {t.get('max_consecutive_losses', 0)}")

        # Risk/Reward
        if 'risk_reward' in metrics:
            rr = metrics['risk_reward']
            lines.append("\n💰 RISK/REWARD ANALYSIS:")
            lines.append(f"  Avg R:R Achieved: {rr.get('avg_risk_reward', 0):.2f}")
            lines.append(f"  Avg MFE: {rr.get('avg_mfe_pct', 0):.2f}%")
            lines.append(f"  Avg MAE: {rr.get('avg_mae_pct', 0):.2f}%")
            lines.append(f"  MFE/MAE Ratio: {rr.get('mfe_mae_ratio', 0):.2f}")

        # Consistency
        if 'consistency' in metrics:
            c = metrics['consistency']
            lines.append("\n🎯 CONSISTENCY:")
            lines.append(f"  Trading Days: {c.get('total_trading_days', 0)}")
            lines.append(f"  Winning Days: {c.get('winning_days', 0)}")
            lines.append(f"  Losing Days: {c.get('losing_days', 0)}")
            lines.append(f"  Daily Win Rate: {c.get('daily_win_rate_pct', 0):.2f}%")
            lines.append(f"  Avg Daily PnL: ${c.get('avg_daily_pnl', 0):+.2f}")
            lines.append(f"  Best Day: ${c.get('best_day', 0):+.2f}")
            lines.append(f"  Worst Day: ${c.get('worst_day', 0):+.2f}")

        # Time Analysis
        if 'time_analysis' in metrics:
            ta = metrics['time_analysis']
            lines.append("\n⏱️  TIME ANALYSIS:")
            lines.append(f"  Avg Trade Duration: {ta.get('avg_trade_duration_bars', 0):.1f} bars")
            lines.append(f"  Avg Win Duration: {ta.get('avg_win_duration_bars', 0):.1f} bars")
            lines.append(f"  Avg Loss Duration: {ta.get('avg_loss_duration_bars', 0):.1f} bars")
            lines.append(f"  Exit Reasons: {ta.get('exit_reasons', {})}")

        lines.append("\n" + "="*60 + "\n")

        return "\n".join(lines)
