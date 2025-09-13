import os
import json
import argparse
import random
from typing import Dict, List, Tuple

import pandas as pd

# Default CheXpert column set (adjust if your CSV differs)
CHEXPERT_COLUMNS = [
    "No Finding", "Enlarged Cardiomediastinum", "Cardiomegaly", "Lung Opacity",
    "Lung Lesion", "Edema", "Consolidation", "Pneumonia", "Atelectasis",
    "Pneumothorax", "Pleural Effusion", "Pleural Other", "Fracture", "Support Devices"
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Map EHR records to CheXpert X-ray paths.")
    ap.add_argument("--ehr_json", required=True, help="Path to EHR JSON (list of patient records).")
    ap.add_argument("--csv", required=True, help="Path to CheXpert CSV (e.g., train_fixed.csv).")
    ap.add_argument("--img_root", default=".", help="Root folder that contains the image paths in CSV.")
    ap.add_argument("--out", default="ehr_with_images.json", help="Output enriched EHR JSON.")
    ap.add_argument("--out_index", default="ehr_image_index.json", help="Output {patient_id: xray_path} index JSON.")
    ap.add_argument("--label_field", default="chexpert_label",
                    help="Field in EHR that stores the CheXpert label to match (default: chexpert_label).")
    ap.add_argument("--path_col", default="Path", help="Column name in CSV that stores image path (default: Path).")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    ap.add_argument("--inplace", action="store_true",
                    help="Overwrite the input EHR JSON in place (creates a .bak backup).")
    ap.add_argument("--enforce_unique", action="store_true",
                    help="Try to assign a unique image per EHR record (best effort).")
    ap.add_argument("--frontal_only", action="store_true",
                    help="If the CSV has 'Frontal/Lateral', keep only rows labeled 'Frontal'.")
    ap.add_argument("--ap_or_pa", choices=["AP", "PA", "any"], default="any",
                    help="If CSV has 'AP/PA', filter to AP, PA, or keep any.")
    return ap.parse_args()


def load_ehr(path: str) -> List[Dict]:
    with open(path, "r") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("EHR JSON must be a list of patient records (dicts).")
    return data


def load_chexpert_csv(
    csv_path: str,
    path_col: str,
    frontal_only: bool,
    ap_or_pa: str
) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if path_col not in df.columns:
        raise ValueError(f"CSV must contain a '{path_col}' column.")
    # Optional view filters
    if frontal_only and "Frontal/Lateral" in df.columns:
        df = df[df["Frontal/Lateral"].str.lower() == "frontal"]
    if "AP/PA" in df.columns and ap_or_pa in ("AP", "PA"):
        df = df[df["AP/PA"].str.upper() == ap_or_pa]
    df = df.reset_index(drop=True)
    return df


def filter_existing_paths(
    df: pd.DataFrame,
    img_root: str,
    path_col: str
) -> pd.DataFrame:
    """Keep only rows whose file exists on disk."""
    exists_mask = df[path_col].astype(str).apply(lambda p: os.path.exists(os.path.join(img_root, p)))
    kept = df[exists_mask].reset_index(drop=True)
    missing = (~exists_mask).sum()
    if missing > 0:
        print(f"[CheXpert] Filtered missing files: kept {len(kept)} / {len(df)} (dropped {missing})")
    else:
        print(f"[CheXpert] All CSV paths exist: {len(kept)} files")
    return kept


def build_label_pools(
    df: pd.DataFrame,
    chexpert_cols: List[str],
    path_col: str
) -> Dict[str, List[str]]:
    """Build mapping label -> list of image paths where that label == 1."""
    pools: Dict[str, List[str]] = {}
    for col in chexpert_cols:
        if col in df.columns:
            pool = df.loc[df[col] == 1, path_col].dropna().astype(str).tolist()
        else:
            pool = []
        pools[col] = pool
    return pools


def pick_image_for_label(
    label: str,
    pools: Dict[str, List[str]],
    all_paths: List[str],
    rng: random.Random,
    used: set,
    enforce_unique: bool
) -> Tuple[str, str]:
    """
    Returns (path, reason) where reason is 'label' if matched by label-pool,
    'fallback' if from all_paths.
    Respects enforce_unique best-effort.
    """
    def choose_from(candidates: List[str]) -> str:
        if not candidates:
            return ""
        if not enforce_unique:
            return rng.choice(candidates)
        # enforce uniqueness: try a few times
        idxs = list(range(len(candidates)))
        rng.shuffle(idxs)
        for i in idxs:
            candidate = candidates[i]
            if candidate not in used:
                used.add(candidate)
                return candidate
        # all used; allow reuse if necessary
        return rng.choice(candidates)

    # 1) Try label pool
    if label and label in pools and pools[label]:
        chosen = choose_from(pools[label])
        if chosen:
            return chosen, "label"

    # 2) Fallback to any
    chosen = choose_from(all_paths)
    return chosen, "fallback" if chosen else ""


def write_json_safely(path: str, obj, backup: bool = False):
    """Atomic-ish write with optional backup when overwriting."""
    if backup and os.path.exists(path):
        bak = path + ".bak"
        import shutil
        shutil.copyfile(path, bak)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    args = parse_args()
    rng = random.Random(args.seed)

    # If inplace, redirect outputs to the same EHR file and derive index name
    if args.inplace:
        args.out = args.ehr_json
        base, _ = os.path.splitext(args.ehr_json)
        args.out_index = base + ".index.json"

    # Load inputs
    ehr = load_ehr(args.ehr_json)
    df = load_chexpert_csv(args.csv, args.path_col, args.frontal_only, args.ap_or_pa)
    df = filter_existing_paths(df, args.img_root, args.path_col)

    # Build pools
    pools = build_label_pools(df, CHEXPERT_COLUMNS, args.path_col)
    all_paths = df[args.path_col].dropna().astype(str).tolist()
    if not all_paths:
        raise ValueError("No valid image paths found after filtering.")

    # Assign images
    used = set()
    stats = {"matched_by_label": 0, "fallback_any": 0, "unknown_label": 0}
    missing_pid = 0
    missing_label = 0

    for rec in ehr:
        pid = rec.get("patient_id")
        if not pid:
            missing_pid += 1
            continue

        label = rec.get(args.label_field)
        if not label:
            missing_label += 1

        # pick image
        chosen, reason = pick_image_for_label(
            label=label if isinstance(label, str) else "",
            pools=pools,
            all_paths=all_paths,
            rng=rng,
            used=used,
            enforce_unique=args.enforce_unique
        )

        if not chosen:
            # absolute fallback if something went wrong
            chosen = rng.choice(all_paths)
            reason = "fallback"

        rec["xray_path"] = chosen
        rec["xray_filename"] = os.path.basename(chosen)

        if reason == "label":
            stats["matched_by_label"] += 1
        elif reason == "fallback":
            stats["fallback_any"] += 1
        else:
            stats["unknown_label"] += 1

    # Write outputs
    write_json_safely(args.out, ehr, backup=args.inplace)

    index = {rec["patient_id"]: rec.get("xray_path") for rec in ehr if rec.get("patient_id")}
    write_json_safely(args.out_index, index, backup=False)

    # Report
    print("✓ Mapping complete")
    print(f"  EHR records: {len(ehr)}")
    if missing_pid:
        print(f"  (warn) Records missing patient_id: {missing_pid}")
    if missing_label:
        print(f"  (warn) Records missing {args.label_field}: {missing_label}")
    print(f"  Matched by label: {stats['matched_by_label']}")
    print(f"  Fallback (any image): {stats['fallback_any']}")
    if args.enforce_unique:
        print(f"  Enforced unique assignment (best-effort). Images used: {len({r.get('xray_path') for r in ehr})}")
    print(f"  Wrote enriched EHR: {args.out}")
    print(f"  Wrote index:        {args.out_index}")


if __name__ == "__main__":
    main()