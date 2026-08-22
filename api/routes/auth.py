# -*- coding: utf-8 -*-
"""Authentication endpoints: login and short-lived WS tickets."""

import logging

from fastapi import (
    APIRouter, Request, Form, HTTPException,
)

from core.auth import (
    DEMO_USER, TOKEN_TTL_MINUTES, WS_TICKET_TTL_SECONDS,
    authenticate, create_access_token, create_ws_ticket,
)
from core.audit import audit_event

log = logging.getLogger("api")

router = APIRouter()

@router.post("/auth/ws-ticket")
def auth_ws_ticket(request: Request):
    """Mint a short-lived WS-scoped ticket for the authenticated session.
    WebSocket URLs carry this instead of the session JWT so proxy access
    logs never see a long-lived credential."""
    user = getattr(request.state, "user", DEMO_USER) or DEMO_USER
    return {"ticket": create_ws_ticket(user.get("username", "demo"), user.get("role", "clinician")),
            "expires_in_seconds": WS_TICKET_TTL_SECONDS}

@router.post("/auth/login")
def auth_login(username: str = Form(...), password: str = Form(...)):
    """Exchange credentials for a bearer token (required in clinical mode)."""
    user = authenticate(username, password)
    if not user:
        audit_event("login_failed", user=username, path="/auth/login", status=401)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user["username"], user["role"])
    audit_event("login", user=username, path="/auth/login", status=200)
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "expires_in_minutes": TOKEN_TTL_MINUTES}
