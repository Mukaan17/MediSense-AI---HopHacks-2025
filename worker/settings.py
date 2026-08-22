# -*- coding: utf-8 -*-
"""arq worker settings. The worker shares the backend image and code; it
imports the same pipeline, so anything the API can compute, a job can."""

import os

from arq.connections import RedisSettings

from core.logging_setup import configure_logging

configure_logging()

from arq import cron  # noqa: E402

from worker.jobs import finalize_report_job, retention_purge_job  # noqa: E402


class WorkerSettings:
    functions = [finalize_report_job]
    # Retention: purge cases older than CASE_RETENTION_DAYS nightly (no-op
    # without the durable store or when retention is 0/unset).
    cron_jobs = [cron(retention_purge_job, hour=4, minute=30)]
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = int(os.getenv("WORKER_MAX_JOBS", "4"))
    job_timeout = int(os.getenv("WORKER_JOB_TIMEOUT_S", "300"))
    keep_result = 3600
