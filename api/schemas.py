# -*- coding: utf-8 -*-
"""Pydantic request bodies."""

import logging
from typing import List, Optional

from pydantic import BaseModel


log = logging.getLogger("api")

class InferRequest(BaseModel):
    utterances: List[str]
    patient_id: Optional[str] = None  # optional hint to bind EHR

class TranscribeIn(BaseModel):
    utterance: str
