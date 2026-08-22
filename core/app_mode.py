# -*- coding: utf-8 -*-
"""Application mode: one codebase, two postures.

demo     - showcases every feature on the bundled synthetic dataset
           (MIMIC-IV Demo records paired with CheXpert images); mocked
           integrations (EHR import/export, knowledge-base toggle) enabled;
           no authentication.
clinical - mocked features refuse, the synthetic EHR dataset is not served
           unless explicitly configured, and authentication is required.

The switch is APP_MODE (default: demo). It is read once at import; changing
modes is a restart, not a runtime toggle.
"""

import os

_VALID = ("demo", "clinical")

APP_MODE = os.getenv("APP_MODE", "demo").strip().lower()
if APP_MODE not in _VALID:
    print(f"[MODE] Unknown APP_MODE '{APP_MODE}', falling back to 'demo'")
    APP_MODE = "demo"

DEFAULT_SYNTHETIC_EHR = "ehr_with_images.json"


def is_demo() -> bool:
    return APP_MODE == "demo"


def is_clinical() -> bool:
    return APP_MODE == "clinical"


def ehr_is_synthetic(ehr_json_path: str) -> bool:
    """The bundled dataset pairs MIMIC demo patients with unrelated CheXpert
    images - fine for demos, never for clinical use."""
    return os.path.basename(ehr_json_path or "") == DEFAULT_SYNTHETIC_EHR
