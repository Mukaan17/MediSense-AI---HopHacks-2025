# -*- coding: utf-8 -*-
"""Security middleware: request IDs, upload caps, rate limiting,
clinical-mode auth gate, audit + metrics emission. CORS is installed
here too so the whole HTTP perimeter lives in one module."""

import os
import logging
import threading
import time
from typing import List, Dict

from fastapi import (
    HTTPException,
)
from fastapi.responses import JSONResponse

from core.auth import (
    DEMO_USER, PUBLIC_PATHS, user_from_authorization,
)
from core.audit import audit_event, new_request_id
from core import metrics

log = logging.getLogger("api")

from api.settings import (
    MAX_UPLOAD_MB,
    RATE_LIMIT_PER_MINUTE,
)

_rate_buckets: Dict[str, List[float]] = {}

_rate_lock = threading.Lock()

async def _security_middleware(request, call_next):
    request_id = new_request_id()
    start = time.perf_counter()
    path = request.url.path
    # Routes are dual-mounted at / and /v1; policy checks (public paths,
    # rate-limit exemption, audit patient-id extraction) use the unprefixed
    # form so both mounts behave identically. Audit/metrics keep `path`.
    core_path = path[3:] if path.startswith("/v1/") else path
    # Behind the nginx proxy / ALB every connection shares the proxy's IP;
    # the first X-Forwarded-For hop (set by our nginx) identifies the client.
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    client = forwarded or (request.client.host if request.client else "unknown")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_MB * 1024 * 1024:
        return JSONResponse({"detail": f"Request too large (> {MAX_UPLOAD_MB} MB)"}, status_code=413)
    # A chunked POST with no Content-Length would bypass the size cap;
    # every legitimate client here sends a length.
    if request.method == "POST" and not content_length \
            and "chunked" in (request.headers.get("transfer-encoding") or "").lower():
        return JSONResponse({"detail": "Content-Length required"}, status_code=411)

    if RATE_LIMIT_PER_MINUTE > 0 and core_path != "/health":
        now = time.monotonic()
        with _rate_lock:
            cutoff = now - 60.0
            if len(_rate_buckets) > 10000:
                for key in [k for k, b in _rate_buckets.items() if not b or b[-1] < cutoff]:
                    _rate_buckets.pop(key, None)
            bucket = _rate_buckets.setdefault(client, [])
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= RATE_LIMIT_PER_MINUTE:
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
            bucket.append(now)

    user = DEMO_USER
    if core_path not in PUBLIC_PATHS and not core_path.startswith(("/docs", "/openapi")):
        try:
            user = user_from_authorization(request.headers.get("authorization"))
        except HTTPException as e:
            audit_event("auth_denied", request_id=request_id, method=request.method,
                        path=path, status=e.status_code, detail=str(e.detail))
            return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    request.state.user = user
    request.state.request_id = request_id

    response = await call_next(request)

    # Audit: identifiers and outcomes only - never clinical content.
    duration_ms = (time.perf_counter() - start) * 1000
    patient_id = request.query_params.get("patient_id")
    if not patient_id and core_path.startswith("/ehr/patients/"):
        patient_id = path.rsplit("/", 1)[-1]
    audit_event("request", request_id=request_id, user=user.get("username", ""),
                method=request.method, path=path, status=response.status_code,
                patient_id=patient_id,
                duration_ms=duration_ms)
    # Label metrics with the resolved route template, not the raw path -
    # bounded cardinality, no attacker-controlled label values.
    route_obj = request.scope.get("route")
    route = getattr(route_obj, "path", None) or "unmatched"
    metrics.inc("requests", path=route, status=str(response.status_code))
    metrics.observe("request_latency", duration_ms, path=route)
    response.headers["X-Request-ID"] = request_id
    return response

def install(app) -> None:
    """Install the HTTP perimeter: CORS first (added last = outermost, so
    even early middleware rejections carry CORS headers), then the security
    middleware."""
    app.middleware("http")(_security_middleware)

    from fastapi.middleware.cors import CORSMiddleware

    origins_env = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
    )
    allowed_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
