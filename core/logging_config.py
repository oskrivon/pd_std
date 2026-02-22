"""
Logging Configuration

Configures file and console logging for Ptero Dactyl Studio.
Supports daily rotation and automatic cleanup of old logs.

Usage:
    from core.logging_config import setup_logging

    setup_logging()  # Console only
    setup_logging(log_dir="studio/logs")  # Console + file
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Optional


def setup_logging(
    log_dir: Optional[str | Path] = None,
    level: int = logging.INFO,
    retention_days: int = 7
) -> logging.Logger:
    """
    Setup logging for the studio.

    Args:
        log_dir: Directory for log files. If None, console only.
        level: Logging level (default INFO)
        retention_days: Days to keep old logs (default 7)

    Returns:
        Root logger for studio
    """
    # Create studio logger
    logger = logging.getLogger("studio")
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Format with timestamp
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (always)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if log_dir specified)
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Daily rotation
        log_file = log_path / "daemon.log"
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=retention_days,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y-%m-%d"
        logger.addHandler(file_handler)

        logger.info(f"Logging to {log_file} (retention: {retention_days} days)")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger for a module."""
    return logging.getLogger(f"studio.{name}")


class TaskLogger:
    """
    Logger that writes task execution details to a separate file.
    Each task gets its own log entry with full details.
    """

    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.task_log = self.log_dir / "tasks.log"

    def log_task(
        self,
        task_id: str,
        project: str,
        description: str,
        status: str,
        duration: float,
        error: Optional[str] = None,
        output: Optional[str] = None
    ):
        """Log a task execution."""
        timestamp = datetime.now().isoformat()

        with open(self.task_log, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Task ID: {task_id}\n")
            f.write(f"Project: {project}\n")
            f.write(f"Description: {description}\n")
            f.write(f"Status: {status}\n")
            f.write(f"Duration: {duration:.2f}s\n")

            if error:
                f.write(f"Error: {error}\n")

            if output and len(output) < 500:
                f.write(f"Output: {output}\n")
            elif output:
                f.write(f"Output: {output[:500]}... (truncated)\n")

            f.write(f"{'='*60}\n")
