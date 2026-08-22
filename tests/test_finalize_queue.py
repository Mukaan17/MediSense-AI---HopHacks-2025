"""Finalize job queue: inline default, queued flow, worker job lifecycle,
and the pool-unavailable fallback."""



CANNED = {
    "report": "Advisory case report text.",
    "model": "test-model",
    "fusion": {"top10": [], "top_confidence": 0.0, "margin": 0.0},
    "disclaimer": "Advisory reference only - not a diagnosis. Correlate clinically.",
}


def _case_with_utterance(client) -> str:
    case_id = client.post("/api/case/voice?live=1").json()["case_id"]
    client.post(f"/api/case/{case_id}/transcribe",
                json={"utterance": "persistent cough and fever"})
    return case_id


def test_finalize_requires_utterances(client):
    case_id = client.post("/api/case/voice?live=1").json()["case_id"]
    assert client.post(f"/api/case/{case_id}/finalize").status_code == 400


def test_report_status_404_before_any_request(client):
    case_id = _case_with_utterance(client)
    assert client.get(f"/api/case/{case_id}/report").status_code == 404


def test_inline_mode_returns_complete(client, monkeypatch):
    from api.routes import cases

    async def fake_report(case):
        return dict(CANNED)

    monkeypatch.setattr(cases, "generate_final_report", fake_report)
    case_id = _case_with_utterance(client)
    body = client.post(f"/api/case/{case_id}/finalize").json()
    assert body["status"] == "complete"
    assert body["report"] == CANNED["report"]


def test_queue_mode_enqueues_and_worker_completes(client, monkeypatch):
    from api.routes import cases
    from worker import jobs

    enqueued = []

    class FakePool:
        async def enqueue_job(self, name, *args):
            enqueued.append((name, args))

    async def fake_pool():
        return FakePool()

    async def fake_report(case):
        return dict(CANNED)

    monkeypatch.setenv("FINALIZE_MODE", "queue")
    monkeypatch.setattr(cases, "_get_arq_pool", fake_pool)
    monkeypatch.setattr(jobs, "generate_final_report", fake_report)

    case_id = _case_with_utterance(client)
    body = client.post(f"/api/case/{case_id}/finalize").json()
    assert body["status"] == "queued"
    assert enqueued == [("finalize_report_job", (case_id,))]

    status = client.get(f"/api/case/{case_id}/report").json()
    assert status["status"] == "queued"

    # Run the worker job exactly as arq would.
    import asyncio
    outcome = asyncio.run(jobs.finalize_report_job({}, case_id))
    assert outcome == "complete"

    status = client.get(f"/api/case/{case_id}/report").json()
    assert status["status"] == "complete"
    assert status["report"] == CANNED["report"]


def test_queue_mode_worker_error_is_reported(client, monkeypatch):
    from api.routes import cases
    from worker import jobs

    class FakePool:
        async def enqueue_job(self, name, *args):
            pass

    async def fake_pool():
        return FakePool()

    async def failing_report(case):
        raise RuntimeError("No LLM available for report")

    monkeypatch.setenv("FINALIZE_MODE", "queue")
    monkeypatch.setattr(cases, "_get_arq_pool", fake_pool)
    monkeypatch.setattr(jobs, "generate_final_report", failing_report)

    case_id = _case_with_utterance(client)
    assert client.post(f"/api/case/{case_id}/finalize").json()["status"] == "queued"

    import asyncio
    assert asyncio.run(jobs.finalize_report_job({}, case_id)) == "error"
    status = client.get(f"/api/case/{case_id}/report").json()
    assert status["status"] == "error"
    assert "LLM" in status["error"]


def test_queue_mode_falls_back_inline_without_pool(client, monkeypatch):
    from api.routes import cases

    async def no_pool():
        return None

    async def fake_report(case):
        return dict(CANNED)

    monkeypatch.setenv("FINALIZE_MODE", "queue")
    monkeypatch.setattr(cases, "_get_arq_pool", no_pool)
    monkeypatch.setattr(cases, "generate_final_report", fake_report)

    case_id = _case_with_utterance(client)
    body = client.post(f"/api/case/{case_id}/finalize").json()
    assert body["status"] == "complete"
    assert body["report"] == CANNED["report"]


def test_inline_without_llm_returns_503(client):
    # Keyless environment: the real generate_final_report must surface a
    # clean 503, never a 500.
    case_id = _case_with_utterance(client)
    r = client.post(f"/api/case/{case_id}/finalize")
    assert r.status_code == 503
    assert "LLM" in r.json()["detail"]
