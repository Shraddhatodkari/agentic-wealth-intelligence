"""
Structured (JSON) logging so log output is machine-parseable in a real
deployment (CloudWatch, Datadog, etc.) instead of unstructured print
statements. Every request through the API gets a request_id that ties
its log lines together.
"""

from __future__ import annotations

import json
import logging
import sys
import time

from .config import settings


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "path",
            "status_code",
            "duration_ms",
            "api_key_prefix",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("agentic_wealth_intelligence")
    logger.setLevel(settings.log_level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    return logger


logger = configure_logging()
