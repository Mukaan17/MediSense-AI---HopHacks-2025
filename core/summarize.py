from typing import List


def summarize_live(utterances: List[str], max_words: int = 40) -> str:
    """Lightweight fallback summarizer for live HUD updates.

    Keeps only the latest turns and trims to a hard word budget so websocket
    payloads remain compact and predictable.
    """
    if not utterances:
        return ""

    # Favor recency for live workflows.
    recent = utterances[-4:]
    text = " ".join(str(u).strip() for u in recent if str(u).strip())
    if not text:
        return ""

    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[-max_words:])
