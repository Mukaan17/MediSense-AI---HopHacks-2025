"""API versioning (/v1 dual-mount) and typed response contracts."""


def test_health_served_on_both_mounts(client):
    root = client.get("/health")
    v1 = client.get("/v1/health")
    assert root.status_code == 200
    assert v1.status_code == 200
    assert set(root.json().keys()) == set(v1.json().keys())


def test_health_contract_keys(client):
    body = client.get("/v1/health").json()
    for key in ("status", "app_mode", "ehr_synthetic", "case_store", "top_k",
                "ehr_loaded", "image_model_loaded", "voice_transcription"):
        assert key in body
    assert set(body["voice_transcription"].keys()) == {
        "whisperx_model_loaded", "diarization_model_loaded", "alignment_model_loaded",
    }


def test_openapi_documents_both_mounts(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths
    assert "/v1/health" in paths
    assert "/v1/api/case/{case_id}/finalize" in paths


def test_ehr_patients_on_v1(client):
    r = client.get("/v1/ehr/patients")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["patients"])
    assert body["data_source"] == "synthetic_demo"
    if body["patients"]:
        assert "demographics" in body["patients"][0]


def test_case_create_on_v1_keeps_live_payload(client):
    r = client.post("/v1/api/case/voice?live=1")
    assert r.status_code == 200
    body = r.json()
    assert body["case_id"]
    # extra="allow" must keep the compact-live HUD fields alongside case_id
    assert len(body.keys()) > 1


def test_ws_ticket_contract_on_v1(client):
    r = client.post("/v1/auth/ws-ticket")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"ticket", "expires_in_seconds"}
    assert body["expires_in_seconds"] > 0
