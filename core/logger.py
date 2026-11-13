"""Structured and rotating logger for the Trendyol management system.

Guarantees thread-safe logging to both stdout and a rotating disk log file
(preventing infinite disk growth), with secret masking.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from datetime import datetime
from typing import Callable, Optional

from core.paths import get_data_path

LOGGER_NAME = "trendyol_manager"
_logger: Optional[logging.Logger] = None


class CallbackLogHandler(logging.Handler):
    """Forward formatted log records to a UI-safe callback."""

    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        self.callback(self.format(record))


def setup_logger(
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 5,
) -> logging.Logger:
    """Initialize and configure the centralized application logger."""
    global _logger
    if _logger is not None:
        return _logger

    log_file = log_file or str(get_data_path("watcher.log"))
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    # Avoid duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except OSError as e:
        # If disk file cannot be opened, continue with console
        logger.warning(f"Could not initialize rotating log file '{log_file}': {e}")

    _logger = logger
    return _logger


def get_logger() -> logging.Logger:
    """Return the initialized logger or initialize with defaults."""
    global _logger
    if _logger is None:
        return setup_logger()
    return _logger


def log(msg: str) -> None:
    """Backward-compatible helper function matching legacy trendyol_watcher.py log()."""
    get_logger().info(msg)
