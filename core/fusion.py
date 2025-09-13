import math
from typing import List, Dict, Any
from .config import load_mappings

_map = load_mappings()
IMG2ISSUE = _map.get("imaging_to_issue", {})

def _logit(p: float, eps=1e-6):
    p = min(max(p, eps), 1.0 - eps)
    return math.log(p / (1.0 - p))

def fuse(image_findings: List[Dict[str, Any]], text_findings: List[Dict[str, Any]],
         w_img: float = 0.7, w_txt: float = 0.5, bias: float = 0.0, topk: int = 10):
    txt_logits: Dict[str, float] = {}
    for tf in text_findings:
        lbl = tf["label"]
        txt_logits[lbl] = txt_logits.get(lbl, 0.0) + 1.0

    issue_logits: Dict[str, float] = {}
    for f in image_findings:
        issue = IMG2ISSUE.get(f["label"]) or f.get("label")
        if not issue:
            continue
        issue_logits[issue] = issue_logits.get(issue, 0.0) + w_img * _logit(f["prob"])

    for lbl, tlog in txt_logits.items():
        issue_logits[lbl] = issue_logits.get(lbl, 0.0) + w_txt * tlog

    ranked = []
    for issue, lg in issue_logits.items():
        prob = 1.0 / (1.0 + math.exp(-(lg + bias)))
        ranked.append({"condition": issue, "score": round(prob, 4), "why": "combined evidence"})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:topk]


