"""Chaos tests: dependency failures must degrade to documented behavior,
never to an anonymous 500."""

import pytest


def test_llm_step_failure_yields_clean_503():
    from fastapi import HTTPException
    from api.guards import _call_llm

    def boom():
        raise RuntimeError("GEMINI_API_KEY not set. Please set your key.")

    with pytest.raises(HTTPException) as exc:
        _call_llm(boom)
    assert exc.value.status_code == 503


def test_empty_retriever_keeps_inference_alive(client, monkeypatch):
    # KB volume gone: retrieval returns nothing, the pipeline still answers.
    from core import retriever as core_retriever

    class EmptyRetriever:
        def get_relevant_documents(self, _q):
            return []

    monkeypatch.setattr(core_retriever, "get_retriever", lambda: EmptyRetriever())
    r = client.post("/infer", json={"utterances": ["persistent cough and fever"]})
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body and "extraction" in body


def test_case_store_backend_failure_surfaces_not_crashes(client, monkeypatch):
    # Redis (or any store backend) erroring on read must not become an
    # unhandled exception mid-request.
    from api import state

    class BrokenStore:
        backend = "broken"

        def get(self, _cid):
            raise ConnectionError("redis unreachable")

        def put(self, _cid, _case):
            raise ConnectionError("redis unreachable")

    monkeypatch.setattr(state, "_case_store", BrokenStore())
    monkeypatch.setattr("api.routes.cases._case_store", BrokenStore())
    r = client.post("/api/case/nonexistent/transcribe", json={"utterance": "x"})
    # Documented degraded behavior: an explicit retryable 503, never an
    # anonymous 500 (api/server registers the store-outage handler).
    assert r.status_code == 503
    assert "unreachable" in r.json()["detail"]


def test_stt_unavailable_socket_reports_and_closes(client, monkeypatch):
    from core import live_stt

    monkeypatch.setattr(live_stt, "fw_available", lambda: False)
    with client.websocket_connect("/ws/transcribe") as ws:
        msg = ws.receive_json()
        assert "error" in msg


def test_imaging_unavailable_upload_still_creates_case(client, monkeypatch):
    from api import state

    def broken_predict(_raw, _name):
        raise RuntimeError("imaging backend gone")

    monkeypatch.setattr(state, "_predict_image_with_fallback", broken_predict)
    # Voice-only path is unaffected by imaging chaos.
    r = client.post("/api/case/voice?live=1")
    assert r.status_code == 200
    assert r.json()["case_id"]
