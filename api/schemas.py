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

class QuestionFeedbackIn(BaseModel):
    question: str
    # accepted = the clinician asked it; dismissed = judged not useful.
    # This stream becomes labeled training data for question ranking.
    action: str  # "accepted" | "dismissed"
