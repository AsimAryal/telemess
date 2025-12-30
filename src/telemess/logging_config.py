"""Logging configuration for Telemess."""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Log file location
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "telemess.log"


class TelemessFormatter(logging.Formatter):
    """Custom formatter with colors for console and clean format for files."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        # Get level name padded
        level = record.levelname.ljust(8)

        # Get logger name (shortened)
        name = record.name
        if name.startswith("telemess."):
            name = name[9:]  # Remove 'telemess.' prefix
        name = name[:15].ljust(15)  # Pad/truncate to 15 chars

        # Build message
        message = record.getMessage()

        # Add extra context if present
        extras = []
        for key in ["room_id", "player_id", "player_name", "ip", "action"]:
            if hasattr(record, key) and getattr(record, key):
                extras.append(f"{key}={getattr(record, key)}")

        if extras:
            message = f"[{', '.join(extras)}] {message}"

        if self.use_colors:
            color = self.COLORS.get(record.levelname, "")
            formatted = (
                f"{self.BOLD}{timestamp}{self.RESET} "
                f"{color}{level}{self.RESET} "
                f"\033[90m{name}{self.RESET} "
                f"{message}"
            )
        else:
            formatted = f"{timestamp} {level} {name} {message}"

        # Add exception info if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


def setup_logging(level: str = "INFO", log_to_file: bool = True) -> logging.Logger:
    """
    Set up logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to also log to a file

    Returns:
        The root telemess logger
    """
    # Get the root telemess logger
    logger = logging.getLogger("telemess")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear any existing handlers
    logger.handlers.clear()

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(TelemessFormatter(use_colors=True))
    logger.addHandler(console_handler)

    # File handler without colors
    if log_to_file:
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(TelemessFormatter(use_colors=False))
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module."""
    return logging.getLogger(f"telemess.{name}")


class LogContext:
    """Context manager for adding extra fields to log records."""

    def __init__(
        self,
        logger: logging.Logger,
        room_id: str | None = None,
        player_id: str | None = None,
        player_name: str | None = None,
        ip: str | None = None,
        action: str | None = None,
    ):
        self.logger = logger
        self.extra = {
            "room_id": room_id,
            "player_id": player_id,
            "player_name": player_name,
            "ip": ip,
            "action": action,
        }

    def _log(self, level: int, msg: str, *args, **kwargs):
        # Merge extra fields
        extra = {**self.extra, **kwargs.pop("extra", {})}
        kwargs["extra"] = extra
        self.logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, *args, **kwargs)
