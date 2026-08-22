# -*- coding: utf-8 -*-
"""Logging configuration. LOG_FORMAT=json switches every log line to one
JSON object (timestamp, level, logger, message) for CloudWatch/Loki
ingestion; the default stays human-readable for local development."""

import json
import logging
import os


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    level = os.getenv("LOGLEVEL", "INFO")
    if os.getenv("LOG_FORMAT", "").lower() == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.basicConfig(level=level, handlers=[handler], force=True)
    else:
        logging.basicConfig(level=level)
