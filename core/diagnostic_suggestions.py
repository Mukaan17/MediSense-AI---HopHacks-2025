from typing import Any, Dict, List


def generate_diagnostic_suggestions(
    state: Dict[str, Any],
    max_suggestions: int = 4
) -> Dict[str, Any]:
    """Generate deterministic, low-latency diagnostic hints for live HUD.

    This is intentionally non-LLM to avoid websocket stalls/timeouts.
    """
    top_candidates: List[Dict[str, Any]] = list((state or {}).get("top_candidates") or [])
    top_conf = float((state or {}).get("top_confidence") or 0.0)
    margin = float((state or {}).get("margin") or 0.0)

    ranked = []
    for item in top_candidates[:max_suggestions]:
        cond = item.get("condition")
        if not cond:
            continue
        ranked.append(
            {
                "condition": cond,
                "confidence": float(item.get("score", 0.0)),
                "reason": item.get("why", "Combined multimodal evidence"),
            }
        )

    suggestions = []
    for r in ranked[:max_suggestions]:
        suggestions.append(
            f"Correlate symptoms with {r['condition'].replace('_', ' ')} findings."
        )

    uncertainty_flags = []
    if top_conf < 0.70:
        uncertainty_flags.append("overall_confidence_low")
    if margin < 0.08:
        uncertainty_flags.append("top_differentials_close")

    return {
        "ranked": ranked,
        "diagnostic_suggestions": suggestions,
        "uncertainty_flags": uncertainty_flags,
    }
