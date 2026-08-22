# -*- coding: utf-8 -*-
"""Application mode: one codebase, two postures.

demo     - showcases every feature on the bundled synthetic dataset
           (MIMIC-IV Demo records paired with CheXpert images); mocked
           integrations (EHR import/export, knowledge-base toggle) enabled;
           no authentication.
clinical - mocked features refuse, the synthetic EHR dataset is not served
           unless explicitly configured, and authentication is required.

The switch is APP_MODE (default: demo), read per call so tests and tools can
flip modes without module reloads. Startup validation for clinical mode
lives in the app assembly (api/server.py).
"""

import os

_VALID = ("demo", "clinical")

DEFAULT_SYNTHETIC_EHR = "ehr_with_images.json"


def get_app_mode() -> str:
    mode = os.getenv("APP_MODE", "demo").strip().lower()
    return mode if mode in _VALID else "demo"


def is_demo() -> bool:
    return get_app_mode() == "demo"


def is_clinical() -> bool:
    return get_app_mode() == "clinical"


def ehr_is_synthetic(ehr_json_path: str) -> bool:
    """The bundled dataset pairs MIMIC demo patients with unrelated CheXpert
    images - fine for demos, never for clinical use."""
    return os.path.basename(ehr_json_path or "") == DEFAULT_SYNTHETIC_EHR
