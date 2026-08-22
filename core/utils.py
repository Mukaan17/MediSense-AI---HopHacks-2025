import json
import logging
import re
from typing import Any, Dict, List

log = logging.getLogger("core.utils")

# LLM replies wrap JSON in ```json fences, prose, or both; one parser handles
# every shape so the salvage logic can't drift between call sites.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_llm_json(text: str, default: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort parse of an LLM response expected to contain one JSON object.

    Tries, in order: the raw text, the contents of a ```json fence, and the
    widest ``{...}`` span (covers prose-wrapped and trailing-junk replies).
    Returns ``default`` when nothing yields a dict (truncated output, no
    object present, or JSON that parses to a non-dict).
    """
    if not text or not isinstance(text, str):
        return default

    cleaned = text.strip()
    candidates = [cleaned]

    fence = _FENCE_RE.search(cleaned)
    if fence:
        candidates.append(fence.group(1).strip())

    i, j = cleaned.find("{"), cleaned.rfind("}")
    if i != -1 and j > i:
        candidates.append(cleaned[i : j + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed

    log.warning("parse_llm_json: unrecoverable LLM output (%d chars); using default", len(text))
    return default


def json_sanitize(text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible alias for :func:`parse_llm_json`."""
    return parse_llm_json(text, fallback)


def clamp_confidence(value: Any) -> float:
    try:
        v = float(value)
    except Exception:
        v = 0.0
    return max(0.0, min(v, 1.0))


def top_n(items: List[Any], n: int) -> List[Any]:
    return items[: max(0, n)]
