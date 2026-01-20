"""
Supervision Script - Keeps the bot running 24/7
Automatically restarts the bot if it crashes
Monitors health and logs statistics
"""

import subprocess
import time
import logging
import signal
import os
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/supervisor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BotSupervisor:
    """
    Supervises the trading bot process
    Restarts on crash, monitors health
    """
    
    def __init__(self):
        self.bot_process = None
        self.restart_count = 0
        self.start_time = None
        self.running = True
        self.max_restarts = 10  # Max 10 restarts per hour
        self.restart_window = 3600  # 1 hour window
        self.restart_times = []
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("\n" + "="*70)
        logger.info("🤖 BOT SUPERVISOR STARTED")
        logger.info("="*70)
    
    def _signal_handler(self, sig, frame):
        """Handle shutdown signals"""
        logger.info("\n⚠️  Shutdown signal received")
        self.shutdown()
    
    def run(self):
        """
        Main supervision loop
        """
        while self.running:
            try:
                self._check_restart_rate()
                self._start_bot()
                self._monitor_bot()
            except Exception as e:
                logger.error(f"❌ Supervisor error: {e}", exc_info=True)
                time.sleep(5)
    
    def _check_restart_rate(self):
        """
        Check if we're restarting too frequently
        """
        now = time.time()
        
        # Remove old restart times outside the window
        self.restart_times = [
            t for t in self.restart_times 
            if now - t < self.restart_window
        ]
        
        if len(self.restart_times) >= self.max_restarts:
            logger.critical(
                f"🚨 TOO MANY RESTARTS ({len(self.restart_times)} in {self.restart_window}s)\n"
                f"   Bot may be in a crash loop. Manual intervention required."
            )
            self.running = False
            raise Exception("Restart rate limit exceeded")
        
        self.restart_times.append(now)
    
    def _start_bot(self):
        """
        Start the trading bot process
        """
        self.restart_count += 1
        self.start_time = datetime.now()
        
        logger.info("\n" + "-"*70)
        logger.info(f"🚀 Starting bot (attempt #{self.restart_count})")
        logger.info(f"   Time: {self.start_time}")
        logger.info("-"*70)
        
        try:
            self.bot_process = subprocess.Popen(
                ['python3', 'main.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                cwd=os.getcwd()
            )
            
            logger.info(f"✅ Bot started with PID: {self.bot_process.pid}")
            
        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}")
            time.sleep(5)
    
    def _monitor_bot(self):
        """
        Monitor the bot process
        """
        try:
            # Monitor stdout in real-time
            while self.running:
                # Check if process is still running
                returncode = self.bot_process.poll()
                
                if returncode is not None:
                    # Process has exited
                    logger.warning(f"⚠️  Bot process exited with code: {returncode}")
                    
                    # Get remaining output
                    stdout, stderr = self.bot_process.communicate(timeout=2)
                    
                    if stdout:
                        logger.info(f"Bot stdout: {stdout[-500:]}")
                    if stderr:
                        logger.error(f"Bot stderr: {stderr[-500:]}")
                    
                    # Log uptime
                    uptime = datetime.now() - self.start_time
                    logger.info(f"   Uptime: {uptime}")
                    
                    # Wait before restart
                    logger.info("   Waiting 10 seconds before restart...")
                    time.sleep(10)
                    break
                
                # Read and log output
                try:
                    # Non-blocking read
                    if self.bot_process.stdout:
                        import select
                        ready, _, _ = select.select(
                            [self.bot_process.stdout], [], [], 1
                        )
                        if ready:
                            line = self.bot_process.stdout.readline()
                            if line:
                                logger.info(f"[BOT] {line.rstrip()}")
                except:
                    pass
                
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            logger.info("\n⚠️  Keyboard interrupt in monitor")
            self.shutdown()
        except Exception as e:
            logger.error(f"❌ Monitor error: {e}", exc_info=True)
    
    def shutdown(self):
        """
        Gracefully shut down the bot and supervisor
        """
        logger.info("\n" + "="*70)
        logger.info("🛑 SUPERVISOR SHUTTING DOWN")
        logger.info("="*70)
        
        self.running = False
        
        if self.bot_process and self.bot_process.poll() is None:
            logger.info("Stopping bot process...")
            self.bot_process.terminate()
            
            try:
                self.bot_process.wait(timeout=5)
                logger.info("✅ Bot stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("⚠️  Bot didn't stop, killing forcefully")
                self.bot_process.kill()
                self.bot_process.wait()
        
        logger.info("\n📊 Final Statistics:")
        logger.info(f"   Total restarts: {self.restart_count}")
        logger.info(f"   Session duration: {datetime.now() - self.start_time if self.start_time else 'N/A'}")
        logger.info("\n" + "="*70 + "\n")

def main():
    """
    Main entry point
    """
    supervisor = BotSupervisor()
    supervisor.run()

if __name__ == "__main__":
    main()
