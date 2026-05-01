"""Data logging package for the new CataVerse architecture.

This package contains reusable data loggers and logging utilities used by the
new control/experiments stack. It intentionally avoids the package name
``logging`` to prevent shadowing Python's standard library module.
"""

from __future__ import annotations

import logging

from .mass_spec_logger import MassSpecLogger
from .pressure_logger import PressureLogger
from .temperature_log_writer import TemperatureLogWriter


_LOGGING_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure process-wide logging once.

    Args:
        level: Root logging level to apply when first configured.
    """

    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        logging.getLogger().setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger without implicit global configuration."""

    return logging.getLogger(name)


__all__ = [
    "PressureLogger",
    "TemperatureLogWriter",
    "MassSpecLogger",
    "configure_logging",
    "get_logger",
]
