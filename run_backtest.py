#!/usr/bin/env python3
"""
Backtest Runner Script
Easy-to-use script for running backtests

Usage:
    python run_backtest.py --start 2024-01-01 --end 2024-03-31
    python run_backtest.py --start 2024-01-01 --end 2024-03-31 --name my_test
    python run_backtest.py --start 2024-01-01 --end 2024-03-31 --capital 20000
    python run_backtest.py --quick  # Quick 30-day test
"""

import sys
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backtesting.historical_data_loader import HistoricalDataLoader
from backtesting.backtest_engine import BacktestEngine
from backtesting.performance_metrics import PerformanceMetrics
from backtesting.report_generator import ReportGenerator
import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/backtest.log')
    ]
)

logger = logging.getLogger(__name__)


def run_backtest(start_date: str, end_date: str,
                initial_capital: float = 10000.0,
                run_name: str = None,
                force_refresh: bool = False):
    """
    Run a complete backtest

    Args:
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
        initial_capital: Starting capital in USD
        run_name: Optional name for this backtest run
        force_refresh: If True, re-fetch data from API

    Returns:
        Dict with results
    """
    if run_name is None:
        run_name = f"{start_date}_to_{end_date}"

    logger.info("\n" + "="*80)
    logger.info("🚀 STARTING BACKTEST")
    logger.info("="*80)
    logger.info(f"Run Name: {run_name}")
    logger.info(f"Period: {start_date} to {end_date}")
    logger.info(f"Initial Capital: ${initial_capital:,.2f}")
    logger.info("="*80 + "\n")

    try:
        # Step 1: Load historical data
        logger.info("📥 STEP 1: Loading historical data...")
        data_loader = HistoricalDataLoader()

        # Load ALL timeframes needed by filters (4H, 15m, 5m, 1H for strategies)
        timeframes_to_load = [config.HTF_TIMEFRAME, config.MTF_TIMEFRAME, config.LTF_TIMEFRAME, '1H']
        logger.info(f"   Loading timeframes: {', '.join(timeframes_to_load)}")

        sol_data = data_loader.load_data(
            symbol=config.TRADING_SYMBOL,
            start_date=start_date,
            end_date=end_date,
            timeframes=timeframes_to_load,
            force_refresh=force_refresh
        )

        btc_data = data_loader.load_data(
            symbol=config.REFERENCE_SYMBOL,
            start_date=start_date,
            end_date=end_date,
            timeframes=timeframes_to_load,
            force_refresh=force_refresh
        )

        if not sol_data or not btc_data:
            logger.error("❌ Failed to load data")
            return None

        logger.info("✅ Data loaded successfully\n")

        # Step 2: Run backtest
        logger.info("🎯 STEP 2: Running backtest...")
        engine = BacktestEngine(initial_capital=initial_capital)

        results = engine.run(
            sol_data=sol_data,
            btc_data=btc_data,
            start_date=start_date,
            end_date=end_date
        )

        if not results:
            logger.error("❌ Backtest failed")
            return None

        logger.info("✅ Backtest completed\n")

        # Step 3: Calculate metrics
        logger.info("📊 STEP 3: Calculating performance metrics...")
        metrics = PerformanceMetrics.calculate_all(results, results['all_trades'])
        logger.info("✅ Metrics calculated\n")

        # Step 4: Generate reports
        logger.info("📄 STEP 4: Generating reports...")
        report_gen = ReportGenerator()

        # Generate full text report
        report_file = report_gen.generate_full_report(results, metrics, run_name)
        logger.info(f"✅ Full report: {report_file}")

        # Export trades to CSV
        csv_file = report_gen.export_trades_csv(results['all_trades'], run_name)
        if csv_file:
            logger.info(f"✅ Trades CSV: {csv_file}")

        # Export JSON
        json_file = report_gen.export_json(results, metrics, run_name)
        logger.info(f"✅ Results JSON: {json_file}")

        logger.info("\n")

        # Step 5: Print summary to console
        print("\n" + "="*80)
        print("BACKTEST SUMMARY")
        print("="*80)

        summary = results['summary']
        trades = results['trades']

        print(f"\n💰 RESULTS:")
        print(f"  Initial Capital: ${summary['initial_capital']:,.2f}")
        print(f"  Final Capital: ${summary['final_capital']:,.2f}")
        print(f"  Total PnL: ${summary['total_pnl']:+,.2f}")
        print(f"  Total Return: {summary['total_return_pct']:+.2f}%")
        print(f"  Max Drawdown: {summary['max_drawdown_pct']:.2f}%")

        print(f"\n📊 TRADES:")
        print(f"  Total Signals: {results['signals']['total_signals']}")
        print(f"  Filter Pass Rate: {results['signals']['filter_pass_rate']:.1f}%")
        print(f"  Trades Executed: {trades['total_trades']}")
        print(f"  Wins: {trades['wins']} | Losses: {trades['losses']} | BE: {trades['breakevens']}")
        print(f"  Win Rate: {trades['win_rate']:.2f}%")

        if 'trade_stats' in metrics:
            print(f"\n⚡ KEY METRICS:")
            print(f"  Profit Factor: {metrics['trade_stats'].get('profit_factor', 0):.2f}")
            print(f"  Sharpe Ratio: {metrics['risk'].get('sharpe_ratio', 0):.2f}")
            print(f"  Expectancy: ${metrics['trade_stats'].get('expectancy_dollar', 0):.2f}/trade")

        print(f"\n📄 REPORTS:")
        print(f"  Full Report: {report_file}")
        if csv_file:
            print(f"  Trades CSV: {csv_file}")
        print(f"  Results JSON: {json_file}")

        print("\n" + "="*80 + "\n")

        logger.info("✅ BACKTEST COMPLETE!")

        return {
            'results': results,
            'metrics': metrics,
            'reports': {
                'full_report': report_file,
                'csv': csv_file,
                'json': json_file
            }
        }

    except Exception as e:
        logger.error(f"❌ Backtest failed with error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Run backtest for quant trading system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 3-month backtest
  python run_backtest.py --start 2024-01-01 --end 2024-03-31

  # Quick 30-day test
  python run_backtest.py --quick

  # Named backtest with custom capital
  python run_backtest.py --start 2024-01-01 --end 2024-06-30 --name q1_q2_2024 --capital 20000

  # Force refresh data from API
  python run_backtest.py --start 2024-01-01 --end 2024-03-31 --refresh
        """
    )

    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=10000.0, help='Initial capital (default: 10000)')
    parser.add_argument('--name', type=str, help='Name for this backtest run')
    parser.add_argument('--refresh', action='store_true', help='Force refresh data from API')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cache directory before loading data')
    parser.add_argument('--quick', action='store_true', help='Quick 30-day test (last 30 days from today)')
    parser.add_argument('--ai-debug', action='store_true', help='Use Claude AI to debug if no signals generated')
    parser.add_argument('--strategy', type=str, default='breakout',
                       help='Strategy to debug (for --ai-debug) - will auto-detect V3/V2/V1')
    parser.add_argument('--max-iterations', type=int, default=5, help='Max debug iterations (for --ai-debug)')

    args = parser.parse_args()

    # Handle quick mode
    if args.quick:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        run_name = 'quick_test'
        logger.info("🚀 Running quick 30-day backtest")
    else:
        # Validate dates
        if not args.start or not args.end:
            parser.error("--start and --end are required (or use --quick)")

        start_date = args.start
        end_date = args.end
        run_name = args.name

        # Validate date format
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            parser.error("Dates must be in YYYY-MM-DD format")

    # Clear cache if requested
    if args.clear_cache:
        import shutil
        from pathlib import Path
        cache_dir = Path("backtesting/cache")
        if cache_dir.exists():
            logger.info("🗑️  Clearing cache directory...")
            shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("✅ Cache cleared")

    # Run backtest
    result = run_backtest(
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.capital,
        run_name=run_name,
        force_refresh=args.refresh or args.clear_cache
    )

    # If AI debug enabled and no signals, run debug agent
    if args.ai_debug and result:
        signals_generated = result.get('results', {}).get('signals', {}).get('total_signals', 0)
        if signals_generated == 0:
            logger.info("\n" + "="*80)
            logger.info("🤖 AI DEBUG MODE: No signals generated, running Claude debug agent...")
            logger.info("="*80 + "\n")
            
            try:
                from agents.debug_agent import DebugAgent
                
                debugger = DebugAgent(max_iterations=args.max_iterations)
                debug_result = debugger.debug_backtest(
                    start_date,
                    end_date,
                    args.strategy,
                    args.capital
                )
                
                if debug_result['success']:
                    logger.info(f"✅ AI Debug successful: {debug_result['signals_generated']} signals generated")
                    logger.info(f"   Iterations: {debug_result['iterations']}")
                    logger.info(f"   Fixes Applied: {len(debug_result['fixes_applied'])}")
                else:
                    logger.warning(f"⚠️  AI Debug completed but no signals generated after {debug_result['iterations']} iterations")
                
                # Token usage
                usage = debugger.agent.get_token_usage()
                logger.info(f"   Token Usage: {usage['total_tokens']} tokens ({usage['total_requests']} requests)")
                
            except ImportError:
                logger.error("❌ agents package not available. Install anthropic: pip install anthropic")
            except Exception as e:
                logger.error(f"❌ AI Debug failed: {e}", exc_info=True)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
