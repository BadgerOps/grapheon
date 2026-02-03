"""
Enhanced logging utilities for verbose, structured logging.

Provides timing, record counts, and step-by-step progress tracking.
"""

import logging
import time
import sys
from datetime import datetime
from typing import Optional, Any
from contextlib import contextmanager


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'

    def format(self, record):
        # Add color based on level
        color = self.COLORS.get(record.levelname, '')

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Build the message
        level_str = f"{color}{record.levelname:8}{self.RESET}"

        # Add module/function info
        location = f"{record.module}.{record.funcName}" if record.funcName != '<module>' else record.module

        # Format the base message
        message = record.getMessage()

        # Add extra context if available
        extras = []
        for key in ['duration_ms', 'record_count', 'step', 'total_steps', 'progress']:
            if hasattr(record, key):
                value = getattr(record, key)
                if key == 'duration_ms':
                    extras.append(f"duration={value:.1f}ms")
                elif key == 'progress':
                    extras.append(f"progress={value}%")
                elif key == 'step' and hasattr(record, 'total_steps'):
                    extras.append(f"step={value}/{record.total_steps}")
                elif key == 'record_count':
                    extras.append(f"records={value}")

        extra_str = f" [{', '.join(extras)}]" if extras else ""

        return f"{timestamp} | {level_str} | {location:30} | {message}{extra_str}"


def setup_logging(level: str = "DEBUG") -> None:
    """
    Set up enhanced logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Remove existing handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Create console handler with colored formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter())
    handler.setLevel(getattr(logging, level.upper()))

    # Configure root logger
    root.setLevel(getattr(logging, level.upper()))
    root.addHandler(handler)

    # Set specific loggers
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('uvicorn.access').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with enhanced capabilities.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogTimer:
    """
    Context manager for timing operations with automatic logging.

    Usage:
        with LogTimer(logger, "Processing hosts"):
            # ... do work ...

    Or with record count:
        with LogTimer(logger, "Processing hosts") as timer:
            # ... do work ...
            timer.set_record_count(100)
    """

    def __init__(
        self,
        logger: logging.Logger,
        operation: str,
        level: int = logging.INFO,
        step: Optional[int] = None,
        total_steps: Optional[int] = None,
    ):
        self.logger = logger
        self.operation = operation
        self.level = level
        self.step = step
        self.total_steps = total_steps
        self.start_time = None
        self.record_count = None
        self.extra_info = {}

    def __enter__(self):
        self.start_time = time.perf_counter()

        extra = {}
        if self.step is not None:
            extra['step'] = self.step
        if self.total_steps is not None:
            extra['total_steps'] = self.total_steps

        self.logger.log(
            self.level,
            f"Starting: {self.operation}",
            extra=extra
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        extra = {'duration_ms': duration_ms}
        if self.record_count is not None:
            extra['record_count'] = self.record_count
        if self.step is not None:
            extra['step'] = self.step
        if self.total_steps is not None:
            extra['total_steps'] = self.total_steps
        extra.update(self.extra_info)

        if exc_type is not None:
            self.logger.error(
                f"Failed: {self.operation} - {exc_val}",
                extra=extra
            )
        else:
            self.logger.log(
                self.level,
                f"Completed: {self.operation}",
                extra=extra
            )

        return False

    def set_record_count(self, count: int) -> None:
        """Set the number of records processed."""
        self.record_count = count

    def add_info(self, key: str, value: Any) -> None:
        """Add extra info to the completion log."""
        self.extra_info[key] = value


@contextmanager
def log_step(logger: logging.Logger, step: int, total: int, description: str):
    """
    Log a numbered step in a multi-step process.

    Usage:
        with log_step(logger, 1, 5, "Loading configuration"):
            # ... do work ...
    """
    progress = int((step / total) * 100)
    logger.info(
        f"[{step}/{total}] {description}",
        extra={'step': step, 'total_steps': total, 'progress': progress}
    )
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = (time.perf_counter() - start) * 1000
        logger.debug(
            f"[{step}/{total}] {description} - done",
            extra={'duration_ms': duration, 'step': step, 'total_steps': total}
        )


def log_analysis_start(logger: logging.Logger, operation: str, input_size: int) -> float:
    """Log the start of a data analysis operation."""
    logger.info(
        f"Analysis started: {operation}",
        extra={'record_count': input_size}
    )
    return time.perf_counter()


def log_analysis_complete(
    logger: logging.Logger,
    operation: str,
    start_time: float,
    input_count: int,
    output_count: int,
    details: Optional[dict] = None
) -> None:
    """Log the completion of a data analysis operation."""
    duration_ms = (time.perf_counter() - start_time) * 1000

    msg = f"Analysis complete: {operation}"
    if details:
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
        msg = f"{msg} ({detail_str})"

    logger.info(
        msg,
        extra={
            'duration_ms': duration_ms,
            'record_count': output_count,
        }
    )

    # Log throughput for larger operations
    if input_count > 100 and duration_ms > 0:
        throughput = (input_count / duration_ms) * 1000
        logger.debug(f"Throughput: {throughput:.0f} records/sec")
