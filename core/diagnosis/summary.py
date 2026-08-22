# -*- coding: utf-8 -*-
"""Brief working-diagnosis summary (1-2 advisory sentences)."""

import json
from typing import Any, Dict, List, Optional

from ..llm_client import get_llm


def generate_brief_diagnosis_summary(
    extraction: Dict[str, Any],
    fusion_results: Optional[List[Dict[str, Any]]] = None,
    max_sentences: int = 2
) -> str:
    """
    Produce a concise 1–2 line diagnostic summary using LLM knowledge, grounded in
    extracted findings and (optionally) fused image/text candidates.
    """
    extracted_json = json.dumps(extraction.get("extracted", {}))
    top_lines = []
    for i, r in enumerate((fusion_results or [])[:3], 1):
        cond = r.get("condition", "")
        sc = r.get("score", 0.0)
        if cond:
            top_lines.append(f"{i}. {cond} ({sc:.2f})")
    top_text = "\n".join(top_lines)

    prompt = (
        "You are a careful clinical summarizer. Given structured extraction and top candidates, "
        f"write <= {max_sentences} sentences that neutrally summarize the likely working diagnosis. "
        "Do NOT prescribe. Be concise and advisory.\n\n"
        f"Extracted: {extracted_json}\n"
        f"Top candidates:\n{top_text}\n\n"
        "Summary:"
    )
    try:
        llm = get_llm()
        out = llm.invoke(prompt)
        text = (getattr(out, "content", None) or str(out)).strip()
        # Hard truncate to ~300 chars for safety
        return text[:300]
    except Exception:
        return "Concise diagnostic summary is unavailable right now."
