# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 15:55:53
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 16:06:22
import time
import json
import requests
import sys

URL = "http://localhost:8000/multimodal_infer"
IMG = sys.argv[1] if len(sys.argv) > 1 else "train/patient00005/study1/view1_frontal.jpg"

utterances = []

def push_utterance(text):
    utterances.append(text)
    payload = {"utterances": utterances}
    files = {
        "payload": (None, json.dumps(payload), "application/json"),
        "file": ("cxr.jpg", open(IMG, "rb"), "image/jpeg")
    }
    r = requests.post(URL, files=files, timeout=60)
    out = r.json()
    print("\n--- Turn ---")
    print("Last utterance:", text)
    print("Top candidates:", [ (c["condition"], round(c["score"],2)) for c in out["fusion"]["top10"][:3] ])
    print("Coach:", [q["q"] for q in out.get("coach",{}).get("suggested",[]) ])

# Simulate a live dialogue (replace with ASR lines)
push_utterance("patient: fever and cough since yesterday")
time.sleep(2)
push_utterance("doctor: any chest pain or shortness of breath?")
time.sleep(2)
push_utterance("patient: mild shortness of breath, no chest pain")
time.sleep(2)
push_utterance("doctor: sputum? color? any blood?")
time.sleep(2)
push_utterance("patient: yellow sputum, no blood")
