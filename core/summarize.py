# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 22:28:30
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 22:29:59

"""
Live conversation summarization module
"""

from typing import List, Dict, Any


def summarize_live(utterances: List[Dict[str, Any]], max_words: int = 40) -> str:
    """
    Create a brief summary of the conversation for live display.
    
    Args:
        utterances: List of conversation utterances
        max_words: Maximum number of words in the summary
        
    Returns:
        Brief summary string
    """
    if not utterances:
        return ""
    
    # Extract the text from utterances
    texts = []
    for utterance in utterances:
        if isinstance(utterance, dict) and 'text' in utterance:
            texts.append(utterance['text'])
        elif isinstance(utterance, str):
            texts.append(utterance)
    
    # Join all text and create a simple summary
    full_text = " ".join(texts)
    
    # Simple word-based truncation
    words = full_text.split()
    if len(words) <= max_words:
        return full_text
    
    # Truncate and add ellipsis
    summary_words = words[:max_words]
    return " ".join(summary_words) + "..."
