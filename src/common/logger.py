"""
Application logger configuration.
"""

import logging
from pathlib import Path

from configs.settings import LOG_DIR, LOG_LEVEL

# Ensure the log directory exists
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "pc_builder.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger.

    Example:
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)