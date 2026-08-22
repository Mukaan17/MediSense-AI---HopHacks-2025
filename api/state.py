# -*- coding: utf-8 -*-
"""Process state: imaging model, retriever handle, EHR records and
indices (mutated in place so cross-module imports stay valid), the
CheXpert->ontology aliases, and the live-case store."""

import os
import re
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional

from fastapi import (
    HTTPException,
)

from core.retriever import (
    get_retriever, reset as retriever_reset,
)
from core.app_mode import is_clinical, ehr_is_synthetic

log = logging.getLogger("api")

from api.settings import (
    CXR_CKPT,
    EHR_JSON,
)

try:
    from core.imaging import ImagingModel
    _IMAGING_IMPORT_ERROR = None
except Exception as _img_import_exc:  # pragma: no cover - optional dependency fallback
    ImagingModel = None
    _IMAGING_IMPORT_ERROR = str(_img_import_exc)
if ImagingModel is None:
    log.warning(f"[IMG] Imaging dependencies unavailable: {_IMAGING_IMPORT_ERROR}")
elif os.path.exists(CXR_CKPT):
    try:
        _img_model = ImagingModel(ckpt_path=CXR_CKPT)
    except Exception as e:
        log.warning(f"[IMG] Failed to initialize imaging model from {CXR_CKPT}: {e}")
else:
    log.warning(
        f"[IMG] Checkpoint not found at {CXR_CKPT}. "
        "Image endpoints will be unavailable until CXR_CKPT is configured."
    )

from core.case_store import make_case_store

_img_model: Optional[ImagingModel] = None

_retriever = None

def _retriever_instance():
    global _retriever
    if _retriever is None:
        _retriever = get_retriever()
    return _retriever

EHR_RECORDS: List[Dict[str, Any]] = []

EHR_BY_PATIENT: Dict[str, Dict[str, Any]] = {}

EHR_BY_IMAGE_PATH: Dict[str, str] = {}          # normalized xray_path -> patient_id

EHR_BY_IMAGE_BASENAME: Dict[str, List[str]] = {}  # basename -> [patient_id...]

EHR_BY_IMAGE_HASH: Dict[str, str] = {}          # sha256(image bytes) -> patient_id

def _normalize_image_relpath(path: Optional[str]) -> str:
    if not path:
        return ""
    p = str(path).strip().replace("\\", "/")
    p = re.sub(r"^(\./)+", "", p)
    prefix = "CheXpert-v1.0-small/"
    if p.startswith(prefix):
        p = p[len(prefix):]
    if p.startswith("chexpert/"):
        p = p[len("chexpert/"):]
    return p.lstrip("/")

def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()

def _sha256_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

def _candidate_local_image_paths(rel_or_abs_path: str) -> List[str]:
    normalized = _normalize_image_relpath(rel_or_abs_path)
    candidates = [rel_or_abs_path, normalized, os.path.join("chexpert", normalized)]
    out = []
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out

def _append_basename_index(path_like: Optional[str], patient_id: str) -> None:
    if not path_like:
        return
    base = os.path.basename(_normalize_image_relpath(path_like))
    if not base:
        return
    EHR_BY_IMAGE_BASENAME.setdefault(base, [])
    if patient_id not in EHR_BY_IMAGE_BASENAME[base]:
        EHR_BY_IMAGE_BASENAME[base].append(patient_id)

def _ehr_fallback_by_top_label(preds: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    if not preds:
        return None
    top = max(preds, key=lambda x: x.get("score", x.get("prob", 0.0)))
    cxl = top.get("label")
    if not cxl:
        return None
    candidates = [r for r in EHR_RECORDS if r.get("chexpert_label") == cxl]
    return candidates[0] if candidates else None

def _resolve_ehr_from_uploaded_image(
    raw_bytes: Optional[bytes],
    filename: Optional[str],
    preds: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    # 1) Content hash match (most reliable; handles basename collisions)
    if raw_bytes:
        img_hash = _sha256_bytes(raw_bytes)
        pid = EHR_BY_IMAGE_HASH.get(img_hash)
        if pid:
            return EHR_BY_PATIENT.get(pid)

    # 2) Exact path match if client sends a relative path
    norm_name = _normalize_image_relpath(filename)
    if norm_name:
        pid = EHR_BY_IMAGE_PATH.get(norm_name)
        if pid:
            return EHR_BY_PATIENT.get(pid)

    # 3) Basename candidates; disambiguate by top predicted label when available
    base = os.path.basename(norm_name) if norm_name else ""
    if base:
        pids = EHR_BY_IMAGE_BASENAME.get(base, [])
        if len(pids) == 1:
            return EHR_BY_PATIENT.get(pids[0])
        if len(pids) > 1:
            candidates = [EHR_BY_PATIENT.get(pid) for pid in pids if pid in EHR_BY_PATIENT]
            candidates = [c for c in candidates if c]
            if preds:
                top = max(preds, key=lambda x: x.get("score", x.get("prob", 0.0)))
                top_label = top.get("label")
                by_label = [c for c in candidates if c.get("chexpert_label") == top_label]
                if by_label:
                    return by_label[0]
            return candidates[0] if candidates else None

    # 4) Label fallback
    return _ehr_fallback_by_top_label(preds)

def _predict_image_with_fallback(raw_bytes: bytes, filename: Optional[str]) -> List[Dict[str, Any]]:
    # Primary path: model inference.
    if _img_model is not None:
        return _img_model.predict(raw_bytes)

    # Offline fallback: if the uploaded image can be linked to an EHR row, use
    # its recorded label. The score is a fixed placeholder, not model output -
    # flag it so downstream consumers and the UI can say so.
    linked_ehr = _resolve_ehr_from_uploaded_image(raw_bytes, filename, preds=None)
    fallback_label = linked_ehr.get("chexpert_label") if linked_ehr else None
    if fallback_label:
        return [{
            "label": fallback_label,
            "score": 0.60,
            "source": "ehr_linked_label_fallback",
            "fallback": True,
            "note": "Imaging model unavailable; label taken from the linked EHR record, score is a placeholder.",
        }]

    raise HTTPException(
        status_code=503,
        detail="Imaging model unavailable and no EHR-linked fallback label could be resolved for this image."
    )

def _load_ehr() -> None:
    # In-place mutation keeps every from-import of these containers valid.
    EHR_RECORDS.clear(); EHR_BY_PATIENT.clear()
    EHR_BY_IMAGE_PATH.clear(); EHR_BY_IMAGE_BASENAME.clear(); EHR_BY_IMAGE_HASH.clear()
    try:
        with open(EHR_JSON, "r") as f:
            EHR_RECORDS.extend(json.load(f))
        for r in EHR_RECORDS:
            pid = r.get("patient_id")
            if pid:
                EHR_BY_PATIENT[pid] = r
            xpath = r.get("xray_path")
            if xpath:
                norm_xpath = _normalize_image_relpath(xpath)
                r["xray_path"] = norm_xpath
                if norm_xpath and pid:
                    EHR_BY_IMAGE_PATH[norm_xpath] = pid
                    _append_basename_index(norm_xpath, pid)
            if pid:
                _append_basename_index(r.get("xray_filename"), pid)

            # Build a content-hash index for robust matching even when basenames collide.
            if pid and xpath:
                for local_path in _candidate_local_image_paths(xpath):
                    if not os.path.exists(local_path):
                        continue
                    # Hashing every linked image couples startup time to
                    # dataset size; default is skip (set SKIP_HASH=0 to
                    # enable content-hash EHR matching with local images).
                    if os.getenv("SKIP_HASH", "1").strip().lower() not in ("0", "false", "no"):
                        continue
                    digest = _sha256_file(local_path)
                    if not digest:
                        continue
                    EHR_BY_IMAGE_HASH[digest] = pid
                    break
        log.info(f"[EHR] Loaded {len(EHR_RECORDS)} records from {EHR_JSON}")
        log.info(
            f"[EHR] Indexed path={len(EHR_BY_IMAGE_PATH)} "
            f"basename={len(EHR_BY_IMAGE_BASENAME)} hash={len(EHR_BY_IMAGE_HASH)}"
        )
    except FileNotFoundError:
        log.warning(f"[EHR] File not found: {EHR_JSON}. EHR matching will be disabled.")
    except Exception as e:
        log.warning(f"[EHR] Failed to load {EHR_JSON}: {e}")

def _ehr_for_patient(patient_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """EHR lookup honoring the clinical-mode synthetic-data ban: inference
    endpoints must not attach the bundled demo records either."""
    if not patient_id:
        return None
    if is_clinical() and ehr_is_synthetic(EHR_JSON):
        return None
    return EHR_BY_PATIENT.get(patient_id)

ALIASES = {
    "Pleural Effusion": "pleural_effusion_suspected",
    "Atelectasis": "atelectasis",
    "Consolidation": "pneumonia_unspecified",
    "Enlarged Cardiomediastinum": "cardiomegaly",
    "Lung Lesion": "lung_lesion_suspected",
    "Pleural Other": "pleural_other_suspected",
}

_case_store = make_case_store()

def reset_retriever_singleton() -> None:
    """Drop both the core retriever cache and this module's handle so the
    next request re-initializes from disk (used after KB rebuilds)."""
    global _retriever
    retriever_reset()
    _retriever = None



_load_ehr()


def record_case_event(case_id: str, event_type: str, payload=None) -> None:
    """Append to the durable case timeline; a no-op unless the active store
    carries the persistence layer (CASE_DB_URL). Never raises."""
    append = getattr(_case_store, "append_event", None)
    if append is None:
        return
    try:
        append(case_id, event_type, payload or {})
    except Exception:
        pass


def save_case_report(case_id: str, report: str, model=None, fusion=None) -> None:
    """Store a generated report durably; no-op without the persistence layer."""
    save = getattr(_case_store, "save_report", None)
    if save is None:
        return
    try:
        save(case_id, report, model, fusion or {})
    except Exception:
        pass
