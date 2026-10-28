"""File log for the application process."""

from __future__ import annotations

import logging
import os

from foamstudio.core.paths import log_file_path

_CONFIGURED = False


def configure_logging() -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("foamstudio")
    logger.setLevel(logging.INFO)
    if _CONFIGURED:
        return logger
    path = log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if os.environ.get("FOAMSTUDIO_HEADLESS") != "1":
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        logger.addHandler(stream)
    _CONFIGURED = True
    logger.info("Log file: %s", path)
    return logger
