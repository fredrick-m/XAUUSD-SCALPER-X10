"""Structured logging: file + DB events."""
import json
import logging
from typing import Optional

from core.config import LOG_DIR


def get_logger(name: str) -> logging.Logger:
    """Get a named logger that writes to file and console."""
    logger = logging.getLogger(f"agent.{name}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(ch)

    log_file = LOG_DIR / "system.log"
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    ))
    logger.addHandler(fh)

    return logger


def log_event(db, agent_id: str, event_type: str, message: str, metadata: Optional[dict] = None):
    """Write a structured event to the events table."""
    meta_json = json.dumps(metadata) if metadata else None
    db.execute(
        "INSERT INTO events (agent_id, event_type, event_message, metadata) VALUES (?, ?, ?, ?)",
        (agent_id, event_type, message, meta_json),
    )
