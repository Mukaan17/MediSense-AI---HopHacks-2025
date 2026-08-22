# -*- coding: utf-8 -*-
"""SMART-on-FHIR connector (Backend Services profile).

Clinical mode refuses the synthetic dataset by design, which leaves it
without EHR until a real source exists - this package is that source.

    EHR_SOURCE=fhir
    FHIR_BASE_URL=https://fhir.example.org/R4
    FHIR_TOKEN_URL=...        (or discovered from /.well-known/smart-configuration)
    FHIR_CLIENT_ID=...
    FHIR_PRIVATE_KEY_PATH=... (RS384 PEM registered with the EHR)
    FHIR_PATIENT_IDS=id1,id2  (pilot roster)

Verified against a stub server in tests; live verification needs an EHR
sandbox registration (owner-provided - see docs/IMPLEMENTATION_PLAN.md I12).
"""

from .client import FHIRClient  # noqa: F401
from .mapping import ehr_record_from_bundles  # noqa: F401
from .loader import fhir_enabled, load_fhir_records, write_report_document  # noqa: F401
