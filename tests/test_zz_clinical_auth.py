"""Clinical-mode auth tests. Mode and auth config are read per call, so
these tests flip APP_MODE with plain environment variables - no module
reloads - against the same app object the demo tests use. Named zz_ only
so the mode flip runs after the demo-mode modules."""

import json
import os

import pytest


@pytest.fixture(scope="module")
def clinical_client(tmp_path_factory):
    users_file = tmp_path_factory.mktemp("auth") / "users.json"
    os.environ["APP_MODE"] = "clinical"
    os.environ["AUTH_SECRET_KEY"] = "t" * 64
    os.environ["AUTH_USERS_FILE"] = str(users_file)
    # TestClient speaks plain http; Secure cookies wouldn't be replayed.
    os.environ["AUTH_COOKIE_SECURE"] = "false"

    from core.auth import hash_password
    users_file.write_text(json.dumps(
        {"drtest": {"password_hash": hash_password("correct-horse-9"), "role": "clinician"}}))

    from api.server import app
    from fastapi.testclient import TestClient
    yield TestClient(app)

    os.environ["APP_MODE"] = "demo"
    os.environ.pop("AUTH_USERS_FILE", None)
    os.environ.pop("AUTH_COOKIE_SECURE", None)


def test_health_stays_public(clinical_client):
    r = clinical_client.get("/health")
    assert r.status_code == 200
    assert r.json()["app_mode"] == "clinical"


def test_unauthenticated_rejected(clinical_client):
    assert clinical_client.post("/infer", json={"utterances": ["x"]}).status_code == 401


def test_v1_mount_gated_identically(clinical_client):
    # The auth gate normalizes the /v1 prefix: same 401 on the versioned
    # mount, and /v1/health stays public.
    assert clinical_client.post("/v1/infer", json={"utterances": ["x"]}).status_code == 401
    assert clinical_client.get("/v1/health").status_code == 200


def test_bad_credentials_rejected(clinical_client):
    r = clinical_client.post("/auth/login", data={"username": "drtest", "password": "wrong"})
    assert r.status_code == 401


def test_login_and_authorized_request(clinical_client):
    r = clinical_client.post("/auth/login",
                             data={"username": "drtest", "password": "correct-horse-9"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    authed = clinical_client.post("/infer", json={"utterances": ["persistent cough"]},
                                  headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200


def test_mocks_refused_in_clinical(clinical_client):
    r = clinical_client.post("/auth/login",
                             data={"username": "drtest", "password": "correct-horse-9"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert clinical_client.post("/ehr/import_patient_data",
                                data={"patient_id": "X", "payload": "{}"},
                                headers=headers).status_code == 403
    assert clinical_client.get("/ehr/patients", headers=headers).status_code == 403


def _login(client):
    r = client.post("/auth/login",
                    data={"username": "drtest", "password": "correct-horse-9"})
    assert r.status_code == 200
    return r


def test_login_sets_session_and_csrf_cookies(clinical_client):
    clinical_client.cookies.clear()
    r = _login(clinical_client)
    assert "medisense_session" in r.cookies
    assert "medisense_csrf" in r.cookies
    assert r.json()["csrf_token"] == r.cookies["medisense_csrf"]
    set_cookie = " ".join(r.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookie  # the session cookie is XSS-unreadable
    assert "samesite=strict" in set_cookie


def test_cookie_session_authenticates_get(clinical_client):
    clinical_client.cookies.clear()
    _login(clinical_client)
    # No Authorization header: the cookie carries the session.
    assert clinical_client.get("/auth/me").status_code == 200
    assert clinical_client.get("/ehr/patients").status_code == 403  # synthetic ban, not 401


def test_cookie_mutation_requires_csrf_header(clinical_client):
    clinical_client.cookies.clear()
    r = _login(clinical_client)
    csrf = r.cookies["medisense_csrf"]
    body = {"utterances": ["persistent cough"]}
    denied = clinical_client.post("/infer", json=body)
    assert denied.status_code == 403
    assert "CSRF" in denied.json()["detail"]
    allowed = clinical_client.post("/infer", json=body,
                                   headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 200


def test_bearer_auth_still_works_and_skips_csrf(clinical_client):
    clinical_client.cookies.clear()
    token = _login(clinical_client).json()["access_token"]
    clinical_client.cookies.clear()  # bearer only - no cookies at all
    r = clinical_client.post("/infer", json={"utterances": ["persistent cough"]},
                             headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_ws_ticket_via_cookie_session(clinical_client):
    clinical_client.cookies.clear()
    r = _login(clinical_client)
    ticket = clinical_client.post(
        "/auth/ws-ticket", headers={"X-CSRF-Token": r.cookies["medisense_csrf"]})
    assert ticket.status_code == 200
    assert ticket.json()["ticket"]


def test_logout_clears_session(clinical_client):
    clinical_client.cookies.clear()
    r = _login(clinical_client)
    out = clinical_client.post(
        "/auth/logout", headers={"X-CSRF-Token": r.cookies["medisense_csrf"]})
    assert out.status_code == 200
    clinical_client.cookies.clear()
    assert clinical_client.get("/auth/me").status_code == 401


def test_me_401_without_session(clinical_client):
    clinical_client.cookies.clear()
    assert clinical_client.get("/auth/me").status_code == 401


def test_ws_requires_token(clinical_client):
    with clinical_client.websocket_connect("/ws/transcribe") as ws:
        msg = ws.receive()
        assert msg["type"] == "websocket.close"
        assert msg.get("code") == 4401


def test_inference_never_attaches_synthetic_ehr(clinical_client):
    r = clinical_client.post("/auth/login",
                             data={"username": "drtest", "password": "correct-horse-9"})
    token = r.json()["access_token"]
    resp = clinical_client.post(
        "/infer",
        json={"utterances": ["cough"], "patient_id": "MIMIC_10000032"},
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json().get("ehr") in (None, {}), \
        "clinical mode must not fuse the synthetic demo EHR into inference"


def test_ws_ticket_flow(clinical_client):
    r = clinical_client.post("/auth/login",
                             data={"username": "drtest", "password": "correct-horse-9"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    t = clinical_client.post("/auth/ws-ticket", headers=headers)
    assert t.status_code == 200
    ticket = t.json()["ticket"]
    assert ticket and ticket != token

    # The ticket authenticates a WebSocket (auth passes; the socket then
    # reports STT unavailability or readiness rather than closing 4401).
    with clinical_client.websocket_connect(f"/ws/transcribe?token={ticket}") as ws:
        msg = ws.receive()
        assert not (msg["type"] == "websocket.close" and msg.get("code") == 4401)

    # A WS ticket must NOT work as a REST bearer token (CWE-598 mitigation:
    # a ticket leaked via an access log is useless outside a socket).
    rest = clinical_client.post("/infer", json={"utterances": ["x"]},
                                headers={"Authorization": f"Bearer {ticket}"})
    assert rest.status_code == 401


def test_ws_ticket_requires_auth(clinical_client):
    # No bearer AND no session cookie (earlier tests leave cookies in the
    # shared jar; with a cookie this would be a CSRF 403, not a 401).
    clinical_client.cookies.clear()
    assert clinical_client.post("/auth/ws-ticket").status_code == 401
