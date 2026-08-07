"""Logging that reads like a professional trading journal — every line explains WHY."""

from __future__ import annotations

import logging
import sys
from typing import Optional


class JournalFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        stamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return f"{stamp} | {record.levelname:<7} | {record.name:<28} | {record.getMessage()}"


def configure_logging(level: str = "INFO", logfile: Optional[str] = None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JournalFormatter())
    root.addHandler(stream)

    if logfile:
        file_handler = logging.FileHandler(logfile)
        file_handler.setFormatter(JournalFormatter())
        root.addHandler(file_handler)
