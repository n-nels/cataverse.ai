"""Central logging configuration for CataVerse."""

from __future__ import annotations

import logging


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
