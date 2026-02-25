"""Logging configuration."""
import logging
import logging.handlers
import os
from utils.config import LOG_PATH


def setup_logging(level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger("synctool")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Rotating file handler (5 MB × 3 backups)
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def get_logger(name: str = "synctool") -> logging.Logger:
    return logging.getLogger(name)
