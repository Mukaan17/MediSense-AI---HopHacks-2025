from typing import List, Dict
from .config import load_domains

DOMAINS = load_domains() or {}

def bucket_domains(labels: List[str]) -> Dict[str, List[str]]:
    if not isinstance(DOMAINS, dict) or not DOMAINS:
        return {}
    out = {k: [] for k in DOMAINS}
    for l in labels:
        for k, s in DOMAINS.items():
            if l in s:
                out[k].append(l)
    return out


