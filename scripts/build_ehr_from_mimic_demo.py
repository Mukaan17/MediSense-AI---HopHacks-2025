#!/usr/bin/env python3
"""Build multimodal EHR records from MIMIC-IV Demo + local CheXpert images.

This script replaces synthetic EHR entries with original-source demo records and
links each patient to a real local X-ray path for multimodal inference.
"""

import argparse
import json
import os
import random
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

CHEXPERT_LABELS = [
    "Cardiomegaly",
    "Pleural Effusion",
    "Edema",
    "Consolidation",
    "Pneumonia",
    "Atelectasis",
    "Pneumothorax",
    "Lung Opacity",
    "Lung Lesion",
    "Pleural Other",
    "Enlarged Cardiomediastinum",
    "Fracture",
    "Support Devices",
    "No Finding",
]

LABEL_NOTES = {
    "Cardiomegaly": "Cardiomediastinal silhouette enlargement noted on chest radiograph.",
    "Pleural Effusion": "Pleural fluid layering or blunting of costophrenic angles seen.",
    "Edema": "Interstitial or alveolar edema pattern on chest imaging.",
    "Consolidation": "Focal airspace opacity consistent with consolidation.",
    "Pneumonia": "Pulmonary opacity pattern compatible with possible pneumonia.",
    "Atelectasis": "Subsegmental or lobar volume loss pattern visible.",
    "Pneumothorax": "Pleural line with absent peripheral lung markings.",
    "Lung Opacity": "Nonspecific pulmonary opacity identified.",
    "Lung Lesion": "Focal pulmonary lesion signal present.",
    "Pleural Other": "Non-effusion pleural abnormality signal present.",
    "Enlarged Cardiomediastinum": "Mediastinal/cardiac contour appears enlarged.",
    "Fracture": "Osseous abnormality suggestive of fracture identified.",
    "Support Devices": "Support hardware or lines/tubes visualized.",
    "No Finding": "No acute cardiopulmonary abnormality label from CheXpert metadata.",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mimic-dir",
        default="data_sources/mimic_demo",
        help="Directory containing MIMIC-IV demo CSVs",
    )
    parser.add_argument(
        "--chexpert-train-csv",
        default="chexpert/train.csv",
        help="CheXpert train CSV path",
    )
    parser.add_argument(
        "--chexpert-valid-csv",
        default="chexpert/valid.csv",
        help="CheXpert valid CSV path",
    )
    parser.add_argument(
        "--chexpert-root",
        default="chexpert",
        help="Local root where train/ and valid/ image files exist",
    )
    parser.add_argument(
        "--out",
        default="ehr_with_images.json",
        help="Output EHR JSON file",
    )
    parser.add_argument(
        "--out-index",
        default="ehr_image_index.json",
        help="Output patient->image path JSON index",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic image assignment",
    )
    return parser.parse_args()


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except Exception:
        return None


def _to_height_ft_in(height_inches: Optional[float]) -> Optional[str]:
    if height_inches is None:
        return None
    total_inches = int(round(height_inches))
    feet = total_inches // 12
    inches = total_inches % 12
    return f"{feet}'{inches}\""


def _pick_chexpert_label(row: pd.Series) -> str:
    for label in CHEXPERT_LABELS:
        val = row.get(label)
        if pd.notna(val) and float(val) == 1.0:
            return label
    return "No Finding"


def _load_chexpert_pool(train_csv: str, valid_csv: str, chexpert_root: str) -> pd.DataFrame:
    cols = ["Path"] + CHEXPERT_LABELS
    train_df = pd.read_csv(train_csv, usecols=cols)
    valid_df = pd.read_csv(valid_csv, usecols=cols)
    pool = pd.concat([train_df, valid_df], ignore_index=True)

    def normalize_path(p: str) -> str:
        p = str(p)
        prefix = "CheXpert-v1.0-small/"
        return p[len(prefix):] if p.startswith(prefix) else p

    pool["xray_path"] = pool["Path"].map(normalize_path)
    pool = pool[pool["xray_path"].map(lambda p: os.path.exists(os.path.join(chexpert_root, p)))]
    pool["chexpert_label"] = pool.apply(_pick_chexpert_label, axis=1)
    return pool[["xray_path", "chexpert_label"]].drop_duplicates(subset=["xray_path"]).reset_index(drop=True)


def _latest_admissions(adm_df: pd.DataFrame) -> Dict[int, Dict]:
    work = adm_df.copy()
    work["admittime"] = pd.to_datetime(work["admittime"], errors="coerce")
    work = work.sort_values(["subject_id", "admittime"], ascending=[True, False])
    out: Dict[int, Dict] = {}
    for row in work.itertuples(index=False):
        sid = int(row.subject_id)
        if sid in out:
            continue
        out[sid] = {
            "hadm_id": int(row.hadm_id) if pd.notna(row.hadm_id) else None,
            "admittime": row.admittime.date().isoformat() if pd.notna(row.admittime) else None,
        }
    return out


def _latest_omr(omr_df: pd.DataFrame) -> Dict[int, Dict[str, str]]:
    work = omr_df.copy()
    work["chartdate"] = pd.to_datetime(work["chartdate"], errors="coerce")
    work = work.sort_values(["subject_id", "result_name", "chartdate"], ascending=[True, True, False])
    per_subject: Dict[int, Dict[str, str]] = defaultdict(dict)
    for row in work.itertuples(index=False):
        sid = int(row.subject_id)
        result_name = str(row.result_name)
        if result_name in per_subject[sid]:
            continue
        per_subject[sid][result_name] = str(row.result_value)
    return per_subject


def _diagnoses_by_subject(diag_df: pd.DataFrame, d_icd_df: pd.DataFrame, latest_adm: Dict[int, Dict]) -> Dict[int, List[str]]:
    map_icd = {
        (str(r.icd_code), int(r.icd_version)): str(r.long_title)
        for r in d_icd_df.itertuples(index=False)
    }

    per_subject_all: Dict[int, List[str]] = defaultdict(list)
    per_subject_hadm: Dict[int, List[str]] = defaultdict(list)
    for row in diag_df.itertuples(index=False):
        sid = int(row.subject_id)
        hadm = int(row.hadm_id) if pd.notna(row.hadm_id) else None
        label = map_icd.get((str(row.icd_code), int(row.icd_version)))
        if label:
            per_subject_all[sid].append(label)
            if hadm is not None:
                per_subject_hadm[(sid, hadm)].append(label)

    out: Dict[int, List[str]] = {}
    for sid in set(diag_df["subject_id"].astype(int).tolist()):
        hadm = latest_adm.get(sid, {}).get("hadm_id")
        if hadm is not None:
            picked = per_subject_hadm.get((sid, hadm), [])
        else:
            picked = []
        if not picked:
            picked = per_subject_all.get(sid, [])
        dedup = []
        seen = set()
        for item in picked:
            if item in seen:
                continue
            seen.add(item)
            dedup.append(item)
            if len(dedup) >= 6:
                break
        out[sid] = dedup
    return out


def _meds_by_subject(rx_df: pd.DataFrame, latest_adm: Dict[int, Dict]) -> Dict[int, List[str]]:
    per_subject_all: Dict[int, List[str]] = defaultdict(list)
    per_subject_hadm: Dict[int, List[str]] = defaultdict(list)
    for row in rx_df.itertuples(index=False):
        sid = int(row.subject_id)
        hadm = int(row.hadm_id) if pd.notna(row.hadm_id) else None
        drug = str(row.drug).strip() if pd.notna(row.drug) else ""
        if not drug:
            continue
        per_subject_all[sid].append(drug)
        if hadm is not None:
            per_subject_hadm[(sid, hadm)].append(drug)

    out: Dict[int, List[str]] = {}
    for sid in set(rx_df["subject_id"].astype(int).tolist()):
        hadm = latest_adm.get(sid, {}).get("hadm_id")
        if hadm is not None:
            picked = per_subject_hadm.get((sid, hadm), [])
        else:
            picked = []
        if not picked:
            picked = per_subject_all.get(sid, [])

        dedup = []
        seen = set()
        for item in picked:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(item)
            if len(dedup) >= 8:
                break
        out[sid] = dedup
    return out


def main() -> None:
    args = _parse_args()
    random.seed(args.seed)

    mimic_dir = args.mimic_dir
    patients = pd.read_csv(os.path.join(mimic_dir, "patients.csv"))
    admissions = pd.read_csv(os.path.join(mimic_dir, "admissions.csv"))
    omr = pd.read_csv(os.path.join(mimic_dir, "omr.csv"))
    diagnoses = pd.read_csv(os.path.join(mimic_dir, "diagnoses_icd.csv"))
    d_icd = pd.read_csv(os.path.join(mimic_dir, "d_icd_diagnoses.csv"))
    prescriptions = pd.read_csv(os.path.join(mimic_dir, "prescriptions.csv"))

    latest_adm = _latest_admissions(admissions)
    latest_omr = _latest_omr(omr)
    pmh_map = _diagnoses_by_subject(diagnoses, d_icd, latest_adm)
    meds_map = _meds_by_subject(prescriptions, latest_adm)

    chexpert_pool = _load_chexpert_pool(args.chexpert_train_csv, args.chexpert_valid_csv, args.chexpert_root)
    if len(chexpert_pool) < len(patients):
        raise RuntimeError("Not enough local CheXpert images to link all patient records.")

    image_rows = chexpert_pool.sample(n=len(patients), random_state=args.seed).reset_index(drop=True)

    records: List[Dict] = []
    for i, p in enumerate(patients.sort_values("subject_id").itertuples(index=False)):
        sid = int(p.subject_id)
        img = image_rows.iloc[i]
        omr_values = latest_omr.get(sid, {})

        bp = omr_values.get("Blood Pressure")
        hr = _safe_float(omr_values.get("Heart Rate"))
        rr = _safe_float(omr_values.get("Respiratory Rate"))
        temp_f = _safe_float(omr_values.get("Temperature (F)"))
        spo2 = _safe_float(omr_values.get("Oxygen Saturation"))
        weight_lbs = _safe_float(omr_values.get("Weight (Lbs)"))
        height_inches = _safe_float(omr_values.get("Height (Inches)"))

        encounter_date = latest_adm.get(sid, {}).get("admittime")
        if not encounter_date:
            encounter_date = date(int(p.anchor_year), 1, 1).isoformat()

        label = str(img["chexpert_label"])
        pmh = pmh_map.get(sid, [])
        meds = meds_map.get(sid, [])

        records.append(
            {
                "patient_id": f"MIMIC_{sid}",
                "source": "MIMIC-IV Demo v2.2 (PhysioNet)",
                "source_subject_id": sid,
                "source_hadm_id": latest_adm.get(sid, {}).get("hadm_id"),
                "sex": str(p.gender),
                "age": int(p.anchor_age),
                "vital_signs": {
                    "bp": bp,
                    "hr": hr,
                    "rr": rr,
                    "temp_f": temp_f,
                    "spo2_pct": spo2,
                    "weight_lbs": weight_lbs,
                    "height_in": height_inches,
                    "height_ft_in": _to_height_ft_in(height_inches),
                },
                "pmh": pmh,
                "meds": meds,
                "allergies": [],
                "social": {"tobacco": "unknown", "alcohol": "unknown"},
                "chexpert_label": label,
                "imaging_expectation": LABEL_NOTES.get(label, "Radiographic findings per linked CheXpert label."),
                "ehr_notes": (
                    f"Original-source demo EHR record (subject_id={sid}). "
                    f"Top diagnosis context: {pmh[0] if pmh else 'not available'}."
                ),
                "xray_path": str(img["xray_path"]),
                "xray_filename": os.path.basename(str(img["xray_path"])),
                "encounter_date": encounter_date,
            }
        )

    with open(args.out, "w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    index = {r["patient_id"]: r["xray_path"] for r in records}
    with open(args.out_index, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(records)} records -> {args.out}")
    print(f"Wrote image index -> {args.out_index}")


if __name__ == "__main__":
    main()
