# -*- coding: utf-8 -*-
"""Structured, PHI-conscious audit logging.

Every API request is recorded as one JSON line: who, when, what endpoint,
which patient (identifier only - never conversation or clinical content),
status, and duration. Written to AUDIT_LOG_FILE (default logs/audit.log)
and mirrored to the standard logger.
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

AUDIT_LOG_FILE = os.getenv("AUDIT_LOG_FILE", os.path.join("logs", "audit.log"))

_lock = threading.Lock()
_logger = logging.getLogger("audit")


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def audit_event(event: str, *, request_id: str = "", user: str = "",
                method: str = "", path: str = "", status: Optional[int] = None,
                patient_id: Optional[str] = None, duration_ms: Optional[float] = None,
                detail: Optional[str] = None) -> None:
    record: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": event,
        "request_id": request_id,
        "user": user,
        "method": method,
        "path": path,
    }
    if status is not None:
        record["status"] = status
    if patient_id:
        record["patient_id"] = patient_id
    if duration_ms is not None:
        record["duration_ms"] = round(duration_ms, 1)
    if detail:
        record["detail"] = detail[:300]

    line = json.dumps(record, ensure_ascii=False)
    _logger.info(line)
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_FILE) or ".", exist_ok=True)
        with _lock, open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # never fail a request because the audit file is unwritable
