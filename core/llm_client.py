# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 12:41:23
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:09:36
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

_llm = None

# Load environment variables from .env (project root) if present
load_dotenv()


def get_llm(model: str = None, temperature: float = None):
    global _llm
    if _llm is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set. Please set your GROQ API key in environment variables.")
        model_name = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        temp = float(temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", "0.1"))
        
        try:
            _llm = ChatGroq(
                model=model_name, 
                temperature=temp,
                max_tokens=1024,  # Reduce response length to avoid JSON parsing issues
                timeout=20.0,     # Reduce timeout
                max_retries=1     # Reduce retries
            )
        except Exception as e:
            print(f"Error initializing LLM: {e}")
            # Fallback to a simpler configuration
            _llm = ChatGroq(
                model="llama-3.1-8b-instant",  # Use smaller, faster model
                temperature=temp,
                max_tokens=512,
                timeout=15.0,
                max_retries=1
            )
    return _llm


