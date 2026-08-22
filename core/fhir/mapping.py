# -*- coding: utf-8 -*-
"""R4 resources -> the internal EHR record shape the pipeline already
consumes ({patient_id, age, sex, vital_signs, pmh, meds, allergies,
social, ehr_notes}). Mapping is deliberately lossy-but-safe: anything
unrecognized is dropped, never guessed."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

# LOINC codes for the vitals the pipeline uses.
LOINC_TO_VITAL = {
    "85354-9": "bp",          # blood pressure panel
    "8867-4": "hr",           # heart rate
    "9279-1": "rr",           # respiratory rate
    "8310-5": "temp",         # body temperature
    "2708-6": "spo2_pct",     # oxygen saturation
    "59408-5": "spo2_pct",    # SpO2 by pulse ox
}


def _age_from_birthdate(birth: Optional[str]) -> Optional[int]:
    if not birth:
        return None
    try:
        born = datetime.strptime(birth[:10], "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None


def _sex(patient: Dict[str, Any]) -> Optional[str]:
    gender = (patient.get("gender") or "").lower()
    return {"male": "M", "female": "F"}.get(gender)


def _celsius_to_f(value: float, unit: str) -> float:
    if unit.lower() in ("cel", "c", "°c", "celsius"):
        return round(value * 9 / 5 + 32, 1)
    return value


def _vitals(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Latest value per vital (observations arrive newest-first)."""
    vitals: Dict[str, Any] = {}
    for obs in observations:
        code = next((c.get("code") for c in (obs.get("code", {}).get("coding") or [])
                     if c.get("code") in LOINC_TO_VITAL), None)
        if not code:
            continue
        key = LOINC_TO_VITAL[code]
        if key in vitals or (key == "bp" and "bp" in vitals):
            continue
        if key == "bp":
            sys_v = dia_v = None
            for comp in obs.get("component", []):
                ccode = next((c.get("code") for c in (comp.get("code", {}).get("coding") or [])), "")
                q = comp.get("valueQuantity", {})
                if ccode == "8480-6":
                    sys_v = q.get("value")
                elif ccode == "8462-4":
                    dia_v = q.get("value")
            if sys_v is not None and dia_v is not None:
                vitals["bp"] = f"{int(sys_v)}/{int(dia_v)}"
            continue
        q = obs.get("valueQuantity", {})
        value = q.get("value")
        if value is None:
            continue
        if key == "temp":
            vitals["temp_f"] = _celsius_to_f(float(value), q.get("unit") or q.get("code") or "")
        else:
            vitals[key] = float(value)
    return vitals


def _condition_names(conditions: List[Dict[str, Any]]) -> List[str]:
    out = []
    for c in conditions:
        clinical = ((c.get("clinicalStatus") or {}).get("coding") or [{}])[0].get("code")
        if clinical in ("inactive", "resolved"):
            continue
        text = (c.get("code") or {}).get("text") or next(
            (x.get("display") for x in ((c.get("code") or {}).get("coding") or [])
             if x.get("display")), None)
        if text:
            out.append(text)
    return out


def _medication_names(med_requests: List[Dict[str, Any]]) -> List[str]:
    out = []
    for m in med_requests:
        concept = m.get("medicationCodeableConcept") or {}
        text = concept.get("text") or next(
            (c.get("display") for c in (concept.get("coding") or []) if c.get("display")), None)
        if text:
            out.append(text)
    return out


def _allergy_names(allergies: List[Dict[str, Any]]) -> List[str]:
    out = []
    for a in allergies:
        concept = a.get("code") or {}
        text = concept.get("text") or next(
            (c.get("display") for c in (concept.get("coding") or []) if c.get("display")), None)
        if text:
            out.append(text)
    return out


def ehr_record_from_bundles(patient: Dict[str, Any],
                            conditions: List[Dict[str, Any]],
                            observations: List[Dict[str, Any]],
                            med_requests: List[Dict[str, Any]],
                            allergies: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "patient_id": patient.get("id"),
        "age": _age_from_birthdate(patient.get("birthDate")),
        "sex": _sex(patient),
        "vital_signs": _vitals(observations),
        "pmh": _condition_names(conditions),
        "meds": _medication_names(med_requests),
        "allergies": _allergy_names(allergies),
        "social": {},
        "ehr_notes": None,
        "ehr_source": "fhir",
    }
