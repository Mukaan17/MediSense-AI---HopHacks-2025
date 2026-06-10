import os
import math
import re
from typing import List, Dict, Any
from .config import load_mappings

_map = load_mappings()
_IMG2ISSUE_RAW = _map.get("imaging_to_issue", {})
FUSION_BACKEND = os.getenv("FUSION_BACKEND", "python").strip().lower()

try:
    import torch
except Exception:  # pragma: no cover - optional dependency
    torch = None
try:
    import custom_ops
except Exception:  # pragma: no cover - optional dependency
    custom_ops = None


def _canon_label(v: Any) -> str:
    s = str(v or "").strip().lower()
    if not s:
        return ""
    s = s.replace("/", " ")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


IMG2ISSUE = {
    _canon_label(k): _canon_label(v)
    for k, v in _IMG2ISSUE_RAW.items()
    if _canon_label(k) and _canon_label(v)
}


def _logit(p: float, eps=1e-6):
    p = min(max(p, eps), 1.0 - eps)
    return math.log(p / (1.0 - p))

def fuse(image_findings: List[Dict[str, Any]], text_findings: List[Dict[str, Any]],
         w_img: float = 0.7, w_txt: float = 0.5, bias: float = 0.0, topk: int = 10):
    def _get_prob(d):
        p = d.get("prob")
        if p is None:
            p = d.get("score")
        return p

    txt_logits: Dict[str, float] = {}
    for tf in text_findings:
        lbl = _canon_label(tf.get("label"))
        if not lbl:
            continue
        txt_logits[lbl] = txt_logits.get(lbl, 0.0) + 1.0

    issue_logits: Dict[str, float] = {}
    image_probs_by_issue: Dict[str, List[float]] = {}
    for f in image_findings:
        img_label = _canon_label(f.get("label"))
        issue = IMG2ISSUE.get(img_label) or img_label
        p = _get_prob(f)
        if not issue or p is None:
            continue
        image_probs_by_issue.setdefault(issue, []).append(float(p))
        issue_logits[issue] = issue_logits.get(issue, 0.0) + w_img * _logit(float(p))

    for lbl, tlog in txt_logits.items():
        issue_logits[lbl] = issue_logits.get(lbl, 0.0) + w_txt * tlog

    # Optional CUDA backend using custom_ops kernels.
    use_cuda_backend = (
        FUSION_BACKEND == "cuda"
        and torch is not None
        and custom_ops is not None
        and torch.cuda.is_available()
    )

    if use_cuda_backend and issue_logits:
        issues = list(issue_logits.keys())
        idx = {issue: i for i, issue in enumerate(issues)}
        logits = torch.zeros(len(issues), device="cuda", dtype=torch.float32)

        # Add weighted image logits using CUDA kernel.
        for issue, probs in image_probs_by_issue.items():
            i = idx[issue]
            for p in probs:
                p_vec = torch.full((len(issues),), 0.5, device="cuda", dtype=torch.float32)
                p_vec[i] = float(p)
                custom_ops.weighted_logit(p_vec, logits, float(w_img), 1e-6)

        # Add text logits directly.
        if w_txt != 0:
            txt = torch.tensor([txt_logits.get(issue, 0.0) for issue in issues], device="cuda", dtype=torch.float32)
            logits = logits + (float(w_txt) * txt)

        probs = torch.empty_like(logits)
        custom_ops.sigmoid_bias(logits, probs, float(bias))
        scores = probs.detach().cpu().tolist()
        ranked = [
            {"condition": issue, "score": round(float(score), 4), "why": "combined evidence"}
            for issue, score in zip(issues, scores)
        ]
    else:
        ranked = []
        for issue, lg in issue_logits.items():
            prob = 1.0 / (1.0 + math.exp(-(lg + bias)))
            ranked.append({"condition": issue, "score": round(prob, 4), "why": "combined evidence"})

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:topk]
