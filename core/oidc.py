# -*- coding: utf-8 -*-
"""OIDC login (authorization code + PKCE) for hospital SSO.

    AUTH_MODE=oidc
    OIDC_ISSUER=https://idp.example.org/realms/hospital
    OIDC_CLIENT_ID=medisense
    OIDC_CLIENT_SECRET=...            (confidential client)
    OIDC_REDIRECT_URI=https://app.example.org/auth/oidc/callback
    OIDC_ROLE_CLAIM=roles             (claim carrying role strings)
    OIDC_ADMIN_ROLES=medisense-admin  (values mapping to the admin role)

Flow state (PKCE verifier + nonce) rides a short-lived HS256 JWT in the
`state` parameter - stateless across workers. After the code exchange and
id_token validation, the app issues its own session cookies, so every
downstream check (CSRF, WS tickets, roles) is unchanged.

Verified against a stub IdP in tests; live verification needs the
hospital IdP registration (owner-provided - docs/IMPLEMENTATION_PLAN.md I13).
"""

import base64
import hashlib
import logging
import os
import secrets
import time
from typing import Any, Dict
from urllib.parse import urlencode

import requests

log = logging.getLogger("core.oidc")

STATE_TTL_SECONDS = 600


def oidc_enabled() -> bool:
    return os.getenv("AUTH_MODE", "").strip().lower() == "oidc"


def _cfg(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"OIDC requires {name}")
    return value


_discovery_cache: Dict[str, Dict[str, Any]] = {}


def _discovery() -> Dict[str, Any]:
    issuer = _cfg("OIDC_ISSUER").rstrip("/")
    if issuer not in _discovery_cache:
        resp = requests.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
        resp.raise_for_status()
        _discovery_cache[issuer] = resp.json()
    return _discovery_cache[issuer]


def _state_secret() -> str:
    from .auth import _get_secret
    return _get_secret() or "demo-secret"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_authorization_url() -> str:
    """Authorization redirect with PKCE (S256); verifier + nonce travel in
    a signed, short-lived state JWT."""
    from jose import jwt

    verifier = _b64url(secrets.token_bytes(32))
    nonce = secrets.token_hex(16)
    now = int(time.time())
    state = jwt.encode(
        {"v": verifier, "n": nonce, "iat": now, "exp": now + STATE_TTL_SECONDS,
         "scope": "oidc-state"},
        _state_secret(), algorithm="HS256")

    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    params = {
        "response_type": "code",
        "client_id": _cfg("OIDC_CLIENT_ID"),
        "redirect_uri": _cfg("OIDC_REDIRECT_URI"),
        "scope": os.getenv("OIDC_SCOPES", "openid profile email"),
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{_discovery()['authorization_endpoint']}?{urlencode(params)}"


def _decode_state(state: str) -> Dict[str, Any]:
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(state, _state_secret(), algorithms=["HS256"])
    except JWTError as e:
        raise RuntimeError(f"Invalid OIDC state: {e}")
    if payload.get("scope") != "oidc-state":
        raise RuntimeError("Invalid OIDC state scope")
    return payload


def _map_role(claims: Dict[str, Any]) -> str:
    claim_name = os.getenv("OIDC_ROLE_CLAIM", "roles")
    raw = claims.get(claim_name) or []
    values = raw if isinstance(raw, list) else [raw]
    admin_roles = {r.strip() for r in os.getenv("OIDC_ADMIN_ROLES", "").split(",") if r.strip()}
    return "admin" if admin_roles and any(str(v) in admin_roles for v in values) else "clinician"


def exchange_code(code: str, state: str) -> Dict[str, Any]:
    """Code -> tokens; validates the id_token against the IdP's JWKS and
    the nonce from our state. Returns the internal user dict."""
    from jose import jwt

    payload = _decode_state(state)
    discovery = _discovery()

    resp = requests.post(discovery["token_endpoint"], data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _cfg("OIDC_REDIRECT_URI"),
        "client_id": _cfg("OIDC_CLIENT_ID"),
        "client_secret": os.getenv("OIDC_CLIENT_SECRET", ""),
        "code_verifier": payload["v"],
    }, timeout=10)
    resp.raise_for_status()
    id_token = resp.json()["id_token"]

    jwks = requests.get(discovery["jwks_uri"], timeout=10).json()
    claims = jwt.decode(
        id_token, jwks,
        algorithms=["RS256"],
        audience=_cfg("OIDC_CLIENT_ID"),
        issuer=_cfg("OIDC_ISSUER").rstrip("/"),
        options={"verify_at_hash": False})
    if claims.get("nonce") != payload["n"]:
        raise RuntimeError("OIDC nonce mismatch")

    username = (claims.get("preferred_username") or claims.get("email")
                or claims.get("sub"))
    return {"username": username, "role": _map_role(claims)}
