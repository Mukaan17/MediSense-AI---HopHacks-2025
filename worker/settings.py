# -*- coding: utf-8 -*-
"""arq worker settings. The worker shares the backend image and code; it
imports the same pipeline, so anything the API can compute, a job can."""

import os

from arq.connections import RedisSettings

from core.logging_setup import configure_logging

configure_logging()

from worker.jobs import finalize_report_job  # noqa: E402


class WorkerSettings:
    functions = [finalize_report_job]
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = int(os.getenv("WORKER_MAX_JOBS", "4"))
    job_timeout = int(os.getenv("WORKER_JOB_TIMEOUT_S", "300"))
    keep_result = 3600
