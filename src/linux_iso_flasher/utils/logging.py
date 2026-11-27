"""Log leve em arquivo (XDG state), sem poluir a interface."""

from __future__ import annotations

import logging
from pathlib import Path

from ..core.config import state_home

LOGGER_NAME = "linux_iso_flasher"
_configured = False


def setup_logging(verbose: bool = False) -> logging.Logger:
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        log_dir = state_home() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(log_dir / "flasher.log", encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except OSError:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    _configured = True
    return logger


def get_logger(component: str = "") -> logging.Logger:
    base = setup_logging()
    return base.getChild(component) if component else base
