"""
Structured single-line JSON logger for CloudWatch, Datadog, Splunk, and Loki.
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
from typing import Any, Dict, Optional


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records into single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Extra structured attributes
        if hasattr(record, "structured_data") and isinstance(record.structured_data, dict):
            log_obj.update(record.structured_data)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def get_structured_logger(name: str = "rico") -> logging.Logger:
    """Instantiate structured logger writing to stdout."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(handler)

    return logger
