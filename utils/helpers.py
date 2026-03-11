"""Logging setup and utility helpers."""

import json
import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the entire application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def safe_json_parse(text: str, default=None):
    """Parse JSON string with fallback."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default