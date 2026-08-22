"""API contract tests. Run in demo mode with no LLM keys, no imaging
checkpoint dependencies, and no RAG store required - every endpoint must
degrade gracefully, exactly as a fresh clone behaves."""

import json


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    for key in ("status", "app_mode", "ehr_synthetic", "case_store", "ehr_loaded"):
        assert key in body
    assert body["app_mode"] == "demo"


def test_request_id_header(client):
    r = client.get("/health")
    assert "X-Request-ID" in r.headers


def test_ehr_patients_labeled(client):
    r = client.get("/ehr/patients")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["patients"]) > 0
    assert body["data_source"] == "synthetic_demo"


def test_ehr_patient_404(client):
    assert client.get("/ehr/patients/P001").status_code == 404


def test_infer_degrades_without_llm(client):
    r = client.post("/infer", json={"utterances": ["bad cough and fever for three days"]})
    assert r.status_code == 200
    body = r.json()
    assert "extraction" in body and "answer" in body
    assert "potential_issues_ranked" in body["answer"]


def test_structured_diagnosis_contract(client):
    r = client.post("/structured_diagnosis",
                    data={"payload": json.dumps({"utterances": ["chest pain and shortness of breath"]})})
    assert r.status_code == 200
    body = r.json()
    for key in ("fusion", "evidence", "coach", "risk_analysis", "ehr_integration"):
        assert key in body, f"missing {key}"
    assert "posterior_shift" in body["evidence"]


def test_structured_diagnosis_bad_payload(client):
    assert client.post("/structured_diagnosis", data={"payload": "not-json"}).status_code == 400


def test_voice_transcribe_rejects_non_audio(client):
    r = client.post("/voice_transcribe", files={"file": ("t.txt", b"not audio", "text/plain")})
    assert r.status_code == 400


def test_case_ws_flow(client):
    case_id = client.post("/api/case/voice?live=1").json()["case_id"]
    with client.websocket_connect(f"/ws/case/{case_id}") as ws:
        first = ws.receive_json()
        assert "conf" in first
        ws.send_json({"utterance": "severe cough and high fever", "speaker": "patient"})
        msg = ws.receive_json()
        while msg.get("type") == "streaming_token":
            msg = ws.receive_json()
        assert msg.get("dx"), "HUD must carry a leading condition"
        assert msg.get("transcript_chunk", {}).get("text")
        assert "evidence" in msg


def test_ws_unknown_case(client):
    with client.websocket_connect("/ws/case/nonexistent") as ws:
        assert "error" in ws.receive_json()


def test_finalize_requires_utterances(client):
    case_id = client.post("/api/case/voice?live=1").json()["case_id"]
    assert client.post(f"/api/case/{case_id}/finalize").status_code == 400


def test_finalize_unknown_case(client):
    assert client.post("/api/case/nonexistent/finalize").status_code == 404


def test_voice_case_reflects_in_store(client):
    case_id = client.post("/api/case/voice?live=1").json()["case_id"]
    r = client.post(f"/api/case/{case_id}/transcribe",
                    json={"utterance": "coughing badly", "speaker": "patient"})
    assert r.status_code == 200


def test_demo_mocks_enabled(client):
    assert client.post("/ehr/import_patient_data",
                       data={"patient_id": "X", "payload": "{}"}).status_code == 200
    assert client.post("/knowledge_base/mode", data={"mode": "research"}).status_code == 200


def test_reload_endpoints(client):
    assert client.post("/reload_ehr").status_code == 200
    assert client.post("/reload_retriever").status_code == 200
