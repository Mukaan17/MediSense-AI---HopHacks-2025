# -*- coding: utf-8 -*-
"""Environment-derived tunables shared across the API package."""

import os
import logging



log = logging.getLogger("api")

ASK_THRESH = float(os.getenv("ASK_THRESH", "0.70"))         # ask if top_conf < ASK_THRESH

MARGIN_THRESH = float(os.getenv("MARGIN_THRESH", "0.08"))   # or margin between #1 and #2 < MARGIN_THRESH

MAX_CTX_CHARS = int(os.getenv("MAX_CTX_CHARS", "2000"))     # trim retrieved context for faster processing

EHR_JSON = os.getenv("EHR_JSON", "ehr_with_images.json")    # enriched EHR with xray_path/xray_filename

CXR_CKPT = os.getenv("CXR_CKPT", "checkpoints/biovil_vit_chexpert.pt")

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "240"))

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
