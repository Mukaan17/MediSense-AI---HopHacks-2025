# -*- coding: utf-8 -*-
"""EHR listing and the demo-only import/export mockups."""

import json
import logging
from datetime import datetime

from fastapi import (
    APIRouter, Form, HTTPException,
)

from core.app_mode import ehr_is_synthetic

log = logging.getLogger("api")

from api.settings import (
    EHR_JSON,
)
from api.state import (
    EHR_BY_PATIENT,
    EHR_RECORDS,
)
from api.guards import (
    _demo_only,
    _guard_synthetic_ehr,
)

router = APIRouter()

@router.get("/ehr/patients")
def list_ehr_patients():
    """List all available EHR patients"""
    _guard_synthetic_ehr()
    patients = []
    for record in EHR_RECORDS:
        patients.append({
            "patient_id": record.get("patient_id"),
            "demographics": {
                "age": record.get("age"),
                "sex": record.get("sex")
            },
            "vital_signs": record.get("vital_signs"),
            "pmh": record.get("pmh", []),
            "meds": record.get("meds", []),
            "allergies": record.get("allergies", [])
        })
    return {"patients": patients, "total": len(patients),
            "data_source": ("synthetic_demo" if ehr_is_synthetic(EHR_JSON) else "configured")}

@router.get("/ehr/patients/{patient_id}")
def get_ehr_patient(patient_id: str):
    """Get specific EHR patient data"""
    _guard_synthetic_ehr()
    patient = EHR_BY_PATIENT.get(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"patient": patient}

@router.post("/ehr/import_patient_data")
async def import_patient_data(
    patient_id: str = Form(...),
    payload: str = Form(...)
):
    """
    Import patient data from EHR system (mockup for Epic/Cerner integration)
    """
    _demo_only("EHR import")
    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in payload")
    
    # Mock EHR import - in real implementation, this would connect to Epic/Cerner APIs
    imported_data = {
        "patient_id": patient_id,
        "import_timestamp": datetime.now().isoformat(),
        "source_system": "Epic",  # Could be configurable
        "imported_data": data,
        "status": "imported_successfully"
    }
    
    # In a real implementation, you would:
    # 1. Validate the imported data
    # 2. Store it in your system
    # 3. Update the EHR_BY_PATIENT mapping
    # 4. Return confirmation
    
    return {
        "message": "Patient data imported successfully (mockup)",
        "import_details": imported_data
    }

@router.post("/ehr/export_clinical_summary")
async def export_clinical_summary(
    patient_id: str = Form(...),
    diagnosis_result: str = Form(...)
):
    """
    Export clinical summary back to EHR system (mockup for Epic/Cerner integration)
    """
    _demo_only("Clinical summary export")
    try:
        diagnosis_data = json.loads(diagnosis_result)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in diagnosis_result")
    
    # Mock EHR export - in real implementation, this would send data to Epic/Cerner
    export_data = {
        "patient_id": patient_id,
        "export_timestamp": datetime.now().isoformat(),
        "target_system": "Epic",
        "clinical_summary": diagnosis_data,
        "status": "exported_successfully"
    }
    
    # In a real implementation, you would:
    # 1. Format the data according to EHR standards (HL7 FHIR, etc.)
    # 2. Send via API to the EHR system
    # 3. Handle authentication and authorization
    # 4. Return confirmation
    
    return {
        "message": "Clinical summary exported successfully (mockup)",
        "export_details": export_data
    }
