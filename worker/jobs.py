# -*- coding: utf-8 -*-
"""arq job functions. Jobs communicate results through the shared case
store (Redis in queue deployments), keyed under case['report_job'], so the
API's status endpoint and the worker need no other channel."""

import logging

from api.pipeline import generate_final_report
from api.state import _case_store

log = logging.getLogger("worker")


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
    except Exception as e:
        log.warning(f"[finalize-job] {case_id} failed: {e}")
        case["report_job"] = {"status": "error", "error": str(e)}
    _case_store.put(case_id, case)
    return case["report_job"]["status"]
