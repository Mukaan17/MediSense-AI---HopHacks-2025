# -*- coding: utf-8 -*-
"""Authentication endpoints: login (cookie session + bearer), logout,
session introspection, and short-lived WS tickets."""

import logging

from fastapi import (
    APIRouter, Request, Response, Form, HTTPException,
)

from core.auth import (
    CSRF_COOKIE, DEMO_USER, SESSION_COOKIE, TOKEN_TTL_MINUTES,
    WS_TICKET_TTL_SECONDS, authenticate, cookie_secure, create_access_token,
    create_csrf_token, create_ws_ticket,
)
from core.app_mode import is_clinical
from core.audit import audit_event

log = logging.getLogger("api")

from api.responses import LoginResponse, LogoutResponse, MeResponse, WsTicketResponse

router = APIRouter()

@router.post("/auth/ws-ticket", response_model=WsTicketResponse)
def auth_ws_ticket(request: Request):
    """Mint a short-lived WS-scoped ticket for the authenticated session.
    WebSocket URLs carry this instead of the session JWT so proxy access
    logs never see a long-lived credential."""
    user = getattr(request.state, "user", DEMO_USER) or DEMO_USER
    return {"ticket": create_ws_ticket(user.get("username", "demo"), user.get("role", "clinician")),
            "expires_in_seconds": WS_TICKET_TTL_SECONDS}

def _set_session_cookies(response: Response, user: dict) -> tuple:
    """Issue the httpOnly session cookie + double-submit CSRF cookie for an
    authenticated user; shared by password login and the OIDC callback."""
    token = create_access_token(user["username"], user["role"])
    csrf = create_csrf_token()
    max_age = TOKEN_TTL_MINUTES * 60
    secure = cookie_secure()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                        secure=secure, max_age=max_age, path="/")
    # Deliberately NOT httpOnly: the double-submit pattern needs JS to read
    # this and echo it in the X-CSRF-Token header on mutating requests.
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="strict",
                        secure=secure, max_age=max_age, path="/")
    return token, csrf

@router.post("/auth/login", response_model=LoginResponse)
def auth_login(response: Response, username: str = Form(...), password: str = Form(...)):
    """Exchange credentials for a session. The JWT is set as an httpOnly
    cookie (with a double-submit CSRF cookie) and also returned in the body
    for non-browser API clients using Bearer auth."""
    user = authenticate(username, password)
    if not user:
        audit_event("login_failed", user=username, path="/auth/login", status=401)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token, csrf = _set_session_cookies(response, user)
    audit_event("login", user=username, path="/auth/login", status=200)
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "expires_in_minutes": TOKEN_TTL_MINUTES,
            "csrf_token": csrf}

@router.get("/auth/oidc/login")
def oidc_login():
    """Hospital SSO entry point: redirect to the IdP's authorization
    endpoint (authorization code + PKCE). 503 unless AUTH_MODE=oidc."""
    from fastapi.responses import RedirectResponse
    from core.oidc import build_authorization_url, oidc_enabled
    if not oidc_enabled():
        raise HTTPException(status_code=503, detail="OIDC is not enabled (set AUTH_MODE=oidc)")
    return RedirectResponse(build_authorization_url(), status_code=302)

@router.get("/auth/oidc/callback")
def oidc_callback(code: str, state: str):
    """IdP redirect target: exchange the code, validate the id_token, and
    issue the app's own session cookies (all downstream auth unchanged)."""
    from fastapi.responses import RedirectResponse
    from core.oidc import exchange_code, oidc_enabled
    if not oidc_enabled():
        raise HTTPException(status_code=503, detail="OIDC is not enabled (set AUTH_MODE=oidc)")
    try:
        user = exchange_code(code, state)
    except Exception as e:
        audit_event("login_failed", user="", path="/auth/oidc/callback", status=401,
                    detail=str(e)[:200])
        raise HTTPException(status_code=401, detail=f"OIDC sign-in failed: {e}")
    response = RedirectResponse("/", status_code=302)
    _set_session_cookies(response, user)
    audit_event("login", user=user["username"], path="/auth/oidc/callback", status=200)
    return response

@router.post("/auth/logout", response_model=LogoutResponse)
def auth_logout(request: Request, response: Response):
    """End the cookie session. CSRF-protected like every cookie-authed
    mutation (the middleware enforces it)."""
    user = getattr(request.state, "user", DEMO_USER) or DEMO_USER
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    audit_event("logout", user=user.get("username", ""), path="/auth/logout", status=200)
    return {"status": "logged_out"}

@router.get("/auth/me", response_model=MeResponse)
def auth_me(request: Request):
    """Who am I? 401s in clinical mode without a session - the frontend
    uses that to decide whether to show the login modal."""
    user = getattr(request.state, "user", DEMO_USER) or DEMO_USER
    return {"username": user.get("username", "demo"),
            "role": user.get("role", "clinician"),
            "authenticated": is_clinical()}
