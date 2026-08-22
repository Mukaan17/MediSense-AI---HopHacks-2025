# -*- coding: utf-8 -*-
"""Sentry integration, inert without SENTRY_DSN. Import cost is paid only
when a DSN is configured, so the light/test installs need no sentry-sdk."""

import logging
import os

log = logging.getLogger("core.error_tracking")


def maybe_init_sentry() -> bool:
    """Initialize Sentry when SENTRY_DSN is set; returns whether it did."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("APP_MODE", "demo"),
            release=os.getenv("SENTRY_RELEASE") or None,
            # Error tracking by default; performance tracing stays off
            # unless explicitly enabled (OTel covers tracing here).
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0")),
            # Clinical posture: never attach request bodies or local vars.
            send_default_pii=False,
            include_local_variables=False,
        )
        log.info("[sentry] error tracking enabled")
        return True
    except Exception as e:
        log.warning(f"[sentry] init failed, continuing without: {e}")
        return False
