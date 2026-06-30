"""Structured logging configuration with file rotation."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-8s] %(name)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


def configure_logging(log_dir: Path = Path("./logs"), level: int = logging.INFO) -> None:
    """Initialize application logging with console and rotating file handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("hard_workers")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(_FORMATTER)
    root.addHandler(console)

    _add_file_handler(root, log_dir / "hard_workers.log", logging.DEBUG, max_bytes=10 * 1024 * 1024, backup_count=5)
    _add_file_handler(root, log_dir / "errors.log", logging.ERROR, max_bytes=5 * 1024 * 1024, backup_count=3)

    root.info("Logging configured — log_dir=%s level=%s", log_dir, logging.getLevelName(level))


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'hard_workers' namespace."""
    return logging.getLogger(f"hard_workers.{name}")


def _add_file_handler(
    logger: logging.Logger,
    path: Path,
    level: int,
    max_bytes: int,
    backup_count: int,
) -> None:
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(_FORMATTER)
    logger.addHandler(handler)
