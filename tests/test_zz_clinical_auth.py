"""Clinical-mode auth tests. Named zz_ so they run last: they reload the
server module in clinical mode and restore demo mode afterwards; the other
modules' session client keeps its reference to the demo app object."""

import importlib
import json
import os

import pytest


@pytest.fixture(scope="module")
def clinical_client(tmp_path_factory):
    users_file = tmp_path_factory.mktemp("auth") / "users.json"
    os.environ["APP_MODE"] = "clinical"
    os.environ["AUTH_SECRET_KEY"] = "t" * 64
    os.environ["AUTH_USERS_FILE"] = str(users_file)

    import core.app_mode, core.auth, api.server
    importlib.reload(core.app_mode)
    importlib.reload(core.auth)
    importlib.reload(api.server)

    from core.auth import hash_password
    users_file.write_text(json.dumps(
        {"drtest": {"password_hash": hash_password("correct-horse-9"), "role": "clinician"}}))

    from fastapi.testclient import TestClient
    yield TestClient(api.server.app)

    os.environ["APP_MODE"] = "demo"
    importlib.reload(core.app_mode)
    importlib.reload(core.auth)
    importlib.reload(api.server)


def test_health_stays_public(clinical_client):
    r = clinical_client.get("/health")
    assert r.status_code == 200
    assert r.json()["app_mode"] == "clinical"


def test_unauthenticated_rejected(clinical_client):
    assert clinical_client.post("/infer", json={"utterances": ["x"]}).status_code == 401


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
