# -*- coding: utf-8 -*-
"""Authentication and authorization.

Demo mode: every request passes as an anonymous demo user - the demo stays
frictionless. Clinical mode: JWT bearer auth is required on every endpoint
except /health, /auth/login, and the docs; WebSockets authenticate via a
?token= query parameter (browsers cannot set WS headers).

Users come from a JSON file (AUTH_USERS_FILE, default config/users.json,
gitignored): {"username": {"password_hash": "<bcrypt>", "role": "clinician"}}.
Create entries with scripts/create_user.py. Tokens are signed with
AUTH_SECRET_KEY; clinical mode refuses to start without one.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .app_mode import is_clinical

ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = int(os.getenv("AUTH_TOKEN_TTL_MINUTES", "480"))
WS_TICKET_TTL_SECONDS = int(os.getenv("WS_TICKET_TTL_SECONDS", "60"))

ROLES = ("clinician", "admin")


def _users_file() -> str:
    return os.getenv("AUTH_USERS_FILE", os.path.join("config", "users.json"))


def _get_secret() -> str:
    return os.getenv("AUTH_SECRET_KEY", "")


def validate_clinical_config() -> None:
    """Called at app startup: clinical mode must never serve unsigned."""
    if is_clinical() and not _get_secret():
        raise RuntimeError(
            "APP_MODE=clinical requires AUTH_SECRET_KEY (generate one with: openssl rand -hex 32)")


def _load_users() -> Dict[str, Dict[str, Any]]:
    path = _users_file()
    try:
        with open(path, "r") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[AUTH] Failed to read users file {path}: {e}")
        return {}


def hash_password(password: str) -> str:
    # bcrypt directly (passlib 1.7.4 is unmaintained and breaks against
    # bcrypt>=4). bcrypt operates on the first 72 bytes.
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("ascii"))
    except Exception:
        return False


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = _load_users().get(username)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return None
    role = user.get("role", "clinician")
    return {"username": username, "role": role if role in ROLES else "clinician"}


def create_access_token(username: str, role: str) -> str:
    from jose import jwt
    now = int(time.time())
    payload = {"sub": username, "role": role, "iat": now,
               "exp": now + TOKEN_TTL_MINUTES * 60}
    return jwt.encode(payload, _get_secret() or "demo-secret", algorithm=ALGORITHM)


def create_ws_ticket(username: str, role: str) -> str:
    """Short-lived, WS-scoped token. WebSockets authenticate via a URL query
    parameter (browsers cannot set WS headers), and URLs end up in proxy
    access logs - so the URL carries a ~60s ticket, never the 8h session JWT
    (CWE-598). REST rejects tickets, so a logged one is near-worthless."""
    from jose import jwt
    now = int(time.time())
    payload = {"sub": username, "role": role, "scope": "ws", "iat": now,
               "exp": now + WS_TICKET_TTL_SECONDS}
    return jwt.encode(payload, _get_secret() or "demo-secret", algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(token, _get_secret() or "demo-secret", algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")
    return {"username": payload.get("sub"), "role": payload.get("role", "clinician"),
            "scope": payload.get("scope", "session")}


DEMO_USER = {"username": "demo", "role": "clinician"}

PUBLIC_PATHS = {"/health", "/auth/login", "/docs", "/openapi.json", "/redoc"}


def user_from_authorization(authorization: Optional[str]) -> Dict[str, Any]:
    """Resolve the request user. Demo mode: anonymous demo user. Clinical
    mode: a valid Bearer token is required."""
    if not is_clinical():
        return DEMO_USER
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required (Bearer token)")
    user = decode_token(authorization.split(" ", 1)[1].strip())
    if user.get("scope") == "ws":
        raise HTTPException(status_code=401, detail="WS tickets are not valid for REST requests")
    return user


def user_from_ws_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """WS variant: returns None (caller closes the socket) instead of raising
    when clinical-mode auth fails."""
    if not is_clinical():
        return DEMO_USER
    if not token:
        return None
    try:
        return decode_token(token)
    except HTTPException:
        return None


def require_role(user: Dict[str, Any], roles: List[str]) -> None:
    if is_clinical() and user.get("role") not in roles:
        raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(roles)}")
