#!/usr/bin/env python3
"""
Autonomous Trading Mode
Runs supequant with Claude AI monitoring, analysis, and approval gating

Usage:
  python run_autonomous_trading.py                    # Start autonomous mode
  python run_autonomous_trading.py --analyze-logs     # Analyze historical trades
  python run_autonomous_trading.py --report           # Generate daily report
  python run_autonomous_trading.py --status           # Check system status
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add agents to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agents'))

from claude_autonomous_system import (
    AutonomousTradeSystem,
    TradeAnalyzer,
    PatternLearner,
    TradeGatekeeper
)

logger = logging.getLogger(__name__)


class AutonomousTradingMode:
    """Wraps main trading loop with Claude AI autonomy"""
    
    def __init__(self, auto_approve: bool = False):
        """
        Args:
            auto_approve: If True, trades are auto-approved. If False, Claude gates all trades.
        """
        self.system = AutonomousTradeSystem()
        self.auto_approve = auto_approve
        self.trades_file = Path('logs/paper_trades.jsonl')
        self.last_processed = None
    
    def start(self):
        """Start autonomous trading loop"""
        logger.info("✅ Starting Autonomous Trading Mode")
        logger.info(f"   Mode: {'AUTO-APPROVE' if self.auto_approve else 'CLAUDE-GATING'}")
        logger.info("   Claude AI is monitoring all trades")
        logger.info("   Press Ctrl+C to stop\n")
        
        try:
            while True:
                # 1. Check for new completed trades
                self._process_completed_trades()
                
                # 2. Daily report (once per day)
                self._maybe_generate_daily_report()
                
                # 3. Update system status
                self._log_system_status()
                
                time.sleep(60)  # Check every minute
        
        except KeyboardInterrupt:
            logger.info("\n🚫 Stopping Autonomous Trading Mode")
            self._final_report()
    
    def approve_trade(self, trade: dict) -> bool:
        """Decide whether to execute a trade
        
        Args:
            trade: Trade dict with direction, entry_price, stop_loss, etc.
            
        Returns:
            True if trade should execute, False to block
        """
        if self.auto_approve:
            return True
        
        decision = self.system.approve_trade(trade)
        return decision['approved']
    
    def analyze_trade_result(self, trade: dict, market_context: dict = None):
        """Analyze a completed trade and learn from it"""
        self.system.process_completed_trade(trade, market_context)
    
    def _process_completed_trades(self):
        """Check for new completed trades and analyze them"""
        if not self.trades_file.exists():
            return
        
        try:
            with open(self.trades_file, 'r') as f:
                # Read from last known position
                lines = f.readlines()
            
            # Find new trades since last check
            for line in lines:
                try:
                    trade = json.loads(line)
                    
                    # Check if this is a new completed trade
                    if (trade.get('event_type') == 'exit' and 
                        trade.get('timestamp', '') > (self.last_processed or '')):
                        
                        # Analyze the trade
                        self._analyze_trade(trade)
                        self.last_processed = trade.get('timestamp')
                
                except json.JSONDecodeError:
                    pass
        
        except Exception as e:
            logger.error(f"Error processing trades: {e}")
    
    def _analyze_trade(self, trade: dict):
        """Analyze a single trade for learning"""
        pnl = trade.get('pnl', 0)
        
        if pnl < 0:
            logger.info(f"\n🔍 Analyzing losing trade: {trade.get('trade_id')}")
            logger.info(f"   Loss: ${abs(pnl):.2f}")
            
            result = self.system.process_completed_trade(trade)
            
            if result.get('rule_added'):
                logger.info(f"   🤖 Claude added rejection rule: {result['rule_added']}")
            else:
                logger.info(f"   💡 No new pattern identified")
    
    def _maybe_generate_daily_report(self):
        """Generate daily report once per day"""
        report_file = Path('claude_daily_report.txt')
        today = datetime.now().date()
        
        # Check if we already generated today
        if report_file.exists():
            try:
                with open(report_file, 'r') as f:
                    content = f.read()
                    if f"Report Date: {today}" in content:
                        return
            except:
                pass
        
        # Generate new report
        report = self.system.generate_daily_report()
        report = f"Report Date: {today}\n{report}"
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        logger.info(f"\n📊 Generated daily report: {report_file}")
    
    def _log_system_status(self):
        """Log current system status"""
        status = self.system.get_system_status()
        
        if status['learned_rules'] > 0:
            logger.info(
                f"\n📊 System Status: "
                f"{status['learned_rules']} rules learned, "
                f"{status['total_blocks']} blocks, "
                f"${status['estimated_prevented_loss']:.2f} loss prevented"
            )
    
    def _final_report(self):
        """Generate final report before exit"""
        logger.info("\n" + self.system.generate_daily_report())


def analyze_historical_trades():
    """Batch analyze all historical trades"""
    logger.info("Analyzing all historical trades...")
    
    system = AutonomousTradeSystem()
    trades_file = Path('logs/paper_trades.jsonl')
    
    if not trades_file.exists():
        logger.error(f"No trades file found: {trades_file}")
        return
    
    with open(trades_file, 'r') as f:
        lines = f.readlines()
    
    analyzed = 0
    for line in lines:
        try:
            event = json.loads(line)
            
            if event.get('event_type') == 'exit':
                trade = event
                
                # Only analyze losses
                if trade.get('pnl', 0) < 0:
                    logger.info(f"Analyzing: {trade.get('trade_id')}")
                    system.process_completed_trade(trade)
                    analyzed += 1
        except:
            pass
    
    logger.info(f"\nAnalyzed {analyzed} losing trades")
    logger.info(system.generate_daily_report())


def show_status():
    """Show current system status"""
    system = AutonomousTradeSystem()
    logger.info(system.generate_daily_report())


def main():
    parser = argparse.ArgumentParser(description="Autonomous Trading Mode with Claude AI")
    parser.add_argument('--analyze-logs', action='store_true', help='Analyze historical trade logs')
    parser.add_argument('--report', action='store_true', help='Generate daily report')
    parser.add_argument('--status', action='store_true', help='Show system status')
    parser.add_argument('--auto-approve', action='store_true', help='Auto-approve all trades (no Claude gating)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
    )
    
    try:
        if args.analyze_logs:
            analyze_historical_trades()
        elif args.report:
            show_status()
        elif args.status:
            show_status()
        else:
            # Start autonomous mode
            mode = AutonomousTradingMode(auto_approve=args.auto_approve)
            mode.start()
    
    except KeyboardInterrupt:
        logger.info("\nShutdown requested")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
