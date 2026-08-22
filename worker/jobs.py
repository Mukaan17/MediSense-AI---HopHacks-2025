# -*- coding: utf-8 -*-
"""arq job functions. Jobs communicate results through the shared case
store (Redis in queue deployments), keyed under case['report_job'], so the
API's status endpoint and the worker need no other channel."""

import logging

from api.pipeline import generate_final_report
from api.state import _case_store, record_case_event, save_case_report

log = logging.getLogger("worker")


async def retention_purge_job(ctx) -> int:
    """Nightly retention: delete cases whose last update is older than
    CASE_RETENTION_DAYS. No-op without the durable store or retention=0."""
    import os
    days = int(os.getenv("CASE_RETENTION_DAYS", "0"))
    purge = getattr(_case_store, "purge_older_than", None)
    if days <= 0 or purge is None:
        return 0
    removed = purge(days)
    if removed:
        log.info(f"[retention] purged {removed} cases older than {days}d")
    return removed


async def finalize_report_job(ctx, case_id: str) -> str:
    case = _case_store.get(case_id)
    if not case:
        log.warning(f"[finalize-job] case {case_id} vanished before the job ran")
        return "missing"

    case["report_job"] = {"status": "running"}
    _case_store.put(case_id, case)

    try:
        result = await generate_final_report(case)
        case["report_job"] = {"status": "complete", **result}
        save_case_report(case_id, result.get("report") or "", result.get("model"),
                         result.get("fusion"))
        record_case_event(case_id, "report_generated", {"model": result.get("model")})
    except Exception as e:
        log.warning(f"[finalize-job] {case_id} failed: {e}")
        case["report_job"] = {"status": "error", "error": str(e)}
    _case_store.put(case_id, case)
    return case["report_job"]["status"]
