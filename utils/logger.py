"""
Logging Configuration
Sets up structured logging for the entire system
"""

import logging
import os
from datetime import datetime
from config import LOG_LEVEL, LOG_FILE, LOG_TRADES_FILE, LOG_FILTERS_FILE


def setup_logging():
    """
    Configure logging for the entire application
    Creates separate log files for different components
    """
    # Create logs directory
    os.makedirs('logs', exist_ok=True)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL))

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler (colorful output)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Main log file handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Trades log handler (separate file for trades)
    trades_logger = logging.getLogger('trades')
    trades_handler = logging.FileHandler(LOG_TRADES_FILE)
    trades_handler.setLevel(logging.INFO)
    trades_handler.setFormatter(file_formatter)
    trades_logger.addHandler(trades_handler)

    # Filters log handler (separate file for filter decisions)
    filters_logger = logging.getLogger('filters')
    filters_handler = logging.FileHandler(LOG_FILTERS_FILE)
    filters_handler.setLevel(logging.INFO)
    filters_handler.setFormatter(file_formatter)
    filters_logger.addHandler(filters_handler)

    # Reduce noise from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)

    logging.info("="*60)
    logging.info("🚀 ELITE QUANT SYSTEM STARTING")
    logging.info(f"Timestamp: {datetime.now()}")
    logging.info(f"Log Level: {LOG_LEVEL}")
    logging.info("="*60)
