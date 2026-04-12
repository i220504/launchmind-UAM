from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from config import settings


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class JsonlAuditLogger:
    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: dict[str, Any]) -> None:
        with self.filepath.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=_json_default) + "\n")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    logfile = settings.logs_dir / "runtime.log"
    file_handler = RotatingFileHandler(logfile, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


audit_logger = JsonlAuditLogger(settings.logs_dir / "audit.jsonl")
