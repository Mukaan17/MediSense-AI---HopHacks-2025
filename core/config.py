import json
from pathlib import Path
from typing import Any, Dict
import yaml
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parents[1]
CFG_DIR = BASE_DIR / "config"

# Load .env for RAG_* and other settings
load_dotenv()

def load_labels() -> Dict[str, Any]:
    with open(CFG_DIR / "labels.json", "r") as f:
        return json.load(f)

def load_domains() -> Dict[str, Any]:
    with open(CFG_DIR / "domains.yaml", "r") as f:
        return yaml.safe_load(f)

def load_mappings() -> Dict[str, Any]:
    with open(CFG_DIR / "mappings.yaml", "r") as f:
        return yaml.safe_load(f)

def load_rag() -> Dict[str, Any]:
    with open(CFG_DIR / "rag.yaml", "r") as f:
        data = yaml.safe_load(f)
        # Overlay with environment variables if present
        env_top_k = os.getenv("RAG_TOP_K")
        if env_top_k:
            try:
                data["top_k"] = int(env_top_k)
            except Exception:
                pass
        return data

def load_allowed_labels() -> Dict[str, Any]:
    """Return the union of all labels across domains.yaml.
    Falls back to labels.json if domains.yaml is missing or malformed.
    """
    try:
        domains = load_domains()
        labels = sorted({label for group in domains.values() for label in (group or [])})
        if labels:
            return {"issues_allowed": labels}
    except Exception:
        pass
    # Fallback
    return load_labels()

def load_prompt(name: str) -> str:
    with open(CFG_DIR / "prompts" / f"{name}.j2", "r") as f:
        return f.read()


def load_symptom_map() -> Dict[str, Any]:
    with open(CFG_DIR / "symptom_map.json", "r") as f:
        return json.load(f)


