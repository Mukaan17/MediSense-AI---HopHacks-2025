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
    try:
        with open(CFG_DIR / "labels.json", "r") as f:
            return json.load(f)
    except Exception:
        return {"issues_allowed": []}

def load_domains() -> Dict[str, Any]:
    """Load domain configuration; return empty dict if missing/malformed."""
    try:
        with open(CFG_DIR / "domains.yaml", "r") as f:
            data = yaml.safe_load(f)
            return data or {}
    except Exception:
        return {}

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

def load_models() -> Dict[str, Any]:
    """LLM routing table from config/models.yaml; {} when absent."""
    try:
        with open(CFG_DIR / "models.yaml", "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

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


# StrictUndefined so a typo'd or missing template variable fails loudly at
# render time instead of silently shipping "{{ var }}" to the LLM.
# autoescape stays off: these are LLM prompts, not HTML.
_prompt_env = None

def render_prompt(name: str, **context: Any) -> str:
    """Render config/prompts/<name>.j2 with real Jinja2 semantics."""
    global _prompt_env
    if _prompt_env is None:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
        _prompt_env = Environment(
            loader=FileSystemLoader(str(CFG_DIR / "prompts")),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
    return _prompt_env.get_template(f"{name}.j2").render(**context)


def load_symptom_map() -> Dict[str, Any]:
    try:
        with open(CFG_DIR / "symptom_map.json", "r") as f:
            return json.load(f)
    except Exception:
        return {}

