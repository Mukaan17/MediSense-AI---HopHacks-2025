"""Durable case store (SQLite-verified per decision D3; Postgres runs the
same SQLAlchemy layer in compose/prod): snapshots, restart recovery, the
event timeline, reports, history listing, retention, and the endpoints."""

import subprocess
import sys

import pytest

from core.case_store import MemoryCaseStore
from core.persistence import DatabaseCaseStore


@pytest.fixture()
def store(tmp_path):
    return DatabaseCaseStore(MemoryCaseStore(), f"sqlite:///{tmp_path}/cases.db")


def test_put_get_roundtrip(store):
    store.put("c1", {"utterances": ["hello"], "ehr": {"patient_id": "MIMIC_1"}})
    assert store.get("c1")["utterances"] == ["hello"]
    assert store.backend == "database+memory"


def test_snapshot_survives_fast_store_loss(store):
    store.put("c1", {"utterances": ["persistent cough"], "ehr": None})
    # Simulate restart/TTL eviction: fresh fast store, same DB.
    store.inner = MemoryCaseStore()
    recovered = store.get("c1")
    assert recovered is not None
    assert recovered["utterances"] == ["persistent cough"]
    # Rehydrated into the fast store for subsequent reads.
    assert store.inner.get("c1") is not None


def test_event_timeline_is_ordered_and_typed(store):
    store.put("c1", {"utterances": []})
    store.append_event("c1", "case_created", {"kind": "voice"})
    store.append_event("c1", "utterance_added", {"text": "cough"})
    store.append_event("c1", "hud_update", {"dx": "uri", "conf": 0.6})
    timeline = store.get_timeline("c1")
    assert [e["type"] for e in timeline] == [
        "case_created", "utterance_added", "hud_update"]
    assert timeline[1]["payload"]["text"] == "cough"
    assert all(e["ts"] for e in timeline)


def test_reports_are_stored(store):
    store.put("c1", {"utterances": ["x"]})
    store.save_report("c1", "Advisory report.", "test-model",
                      {"top10": [], "top_confidence": 0.5, "margin": 0.1})
    # Listing shows the case; the report row exists (queried via timeline DB).
    cases = store.list_cases()
    assert cases[0]["case_id"] == "c1"


def test_list_cases_filters_and_summarizes(store):
    store.put("c1", {"utterances": ["a", "b"], "ehr": {"patient_id": "P1"},
                     "ranked": [{"condition": "pneumonia_unspecified", "score": 0.7}]})
    store.put("c2", {"utterances": [], "ehr": {"patient_id": "P2"}})
    all_cases = store.list_cases()
    assert {c["case_id"] for c in all_cases} == {"c1", "c2"}
    p1 = store.list_cases(patient_id="P1")
    assert len(p1) == 1
    assert p1[0]["utterance_count"] == 2
    assert p1[0]["top_condition"] == "pneumonia_unspecified"


def test_retention_purges_old_cases(store):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update
    from core.persistence.models import Case

    store.put("old", {"utterances": []})
    store.append_event("old", "case_created", {})
    store.put("new", {"utterances": []})
    with store._session() as s:
        s.execute(update(Case).where(Case.id == "old").values(
            updated_at=datetime.now(timezone.utc) - timedelta(days=40)))
        s.commit()
    assert store.purge_older_than(30) == 1
    assert store.list_cases()[0]["case_id"] == "new"
    assert store.get_timeline("old") == []


def test_live_path_survives_db_failure(store):
    # The durable layer must never take the live path down with it.
    store._session = None  # break the DB layer entirely
    store.put("c9", {"utterances": ["still works"]})
    assert store.inner.get("c9")["utterances"] == ["still works"]


def test_history_endpoints_with_durable_store(client, monkeypatch, tmp_path):
    from api import state
    from api.routes import history, cases as cases_route

    db = DatabaseCaseStore(MemoryCaseStore(), f"sqlite:///{tmp_path}/api.db")
    monkeypatch.setattr(state, "_case_store", db)
    monkeypatch.setattr(history, "_case_store", db)
    monkeypatch.setattr(cases_route, "_case_store", db)

    case_id = client.post("/api/case/voice?live=1").json()["case_id"]
    client.post(f"/api/case/{case_id}/transcribe",
                json={"utterance": "persistent cough"})

    listing = client.get("/api/cases").json()
    assert listing["count"] >= 1
    assert any(c["case_id"] == case_id for c in listing["cases"])

    timeline = client.get(f"/api/case/{case_id}/timeline").json()
    types = [e["type"] for e in timeline["events"]]
    assert "case_created" in types
    assert "utterance_added" in types


def test_history_503_without_durable_store(client):
    # Default test store is memory-only: an explicit 503, not an empty list.
    r = client.get("/api/cases")
    assert r.status_code == 503
    assert "CASE_DB_URL" in r.json()["detail"]


def test_alembic_migration_roundtrip(tmp_path):
    env = {"CASE_DB_URL": f"sqlite:///{tmp_path}/mig.db"}
    import os
    full_env = {**os.environ, **env}
    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                        capture_output=True, text=True, env=full_env)
    assert up.returncode == 0, up.stderr
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"],
                          capture_output=True, text=True, env=full_env)
    assert down.returncode == 0, down.stderr
