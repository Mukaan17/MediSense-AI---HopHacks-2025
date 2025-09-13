import json
from typing import Any, Dict, List

def json_sanitize(text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        try:
            i, j = text.find("{"), text.rfind("}")
            if i != -1 and j != -1 and j > i:
                return json.loads(text[i:j+1])
        except Exception:
            return fallback
    return fallback

def clamp_confidence(value: Any) -> float:
    try:
        v = float(value)
    except Exception:
        v = 0.0
    return max(0.0, min(v, 1.0))

def top_n(items: List[Any], n: int) -> List[Any]:
    return items[: max(0, n)]


