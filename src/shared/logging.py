"""Shared logging configuration for the MCP server."""

import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging format and level for all modules."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance."""
    return logging.getLogger(name)
