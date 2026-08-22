# -*- coding: utf-8 -*-
"""EHR_SOURCE=fhir loader: pull the pilot roster into the internal EHR
record shape at startup/reload, and write reports back. Failures degrade
to an empty roster with loud logs - clinical mode then simply has no EHR
rather than wrong EHR."""

import logging
import os
from typing import Any, Dict, List

from .client import FHIRClient
from .mapping import ehr_record_from_bundles

log = logging.getLogger("core.fhir")


def fhir_enabled() -> bool:
    return os.getenv("EHR_SOURCE", "file").strip().lower() == "fhir"


def _roster_ids() -> List[str]:
    return [x.strip() for x in os.getenv("FHIR_PATIENT_IDS", "").split(",") if x.strip()]


def load_fhir_records() -> List[Dict[str, Any]]:
    client = FHIRClient()
    records: List[Dict[str, Any]] = []
    for pid in _roster_ids():
        try:
            records.append(ehr_record_from_bundles(
                client.patient(pid),
                client.conditions(pid),
                client.observations(pid),
                client.medication_requests(pid),
                client.allergies(pid),
            ))
        except Exception as e:
            log.warning(f"[FHIR] failed to load patient {pid}: {e}")
    log.info(f"[FHIR] loaded {len(records)}/{len(_roster_ids())} roster patients")
    return records


def write_report_document(patient_id: str, report_text: str) -> bool:
    """DocumentReference write-back for a finalized advisory report."""
    try:
        FHIRClient().create_document_reference(patient_id, report_text)
        return True
    except Exception as e:
        log.warning(f"[FHIR] report write-back failed for {patient_id}: {e}")
        return False
