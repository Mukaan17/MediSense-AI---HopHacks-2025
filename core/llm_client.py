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
            raise RuntimeError("GROQ_API_KEY not set")
        model_name = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        temp = float(temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", "0.1"))
        _llm = ChatGroq(model=model_name, temperature=temp)
    return _llm


