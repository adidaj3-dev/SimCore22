import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "simcore_mvp.log")


def setup_logging(level=logging.INFO):
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Rotating file handler
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
