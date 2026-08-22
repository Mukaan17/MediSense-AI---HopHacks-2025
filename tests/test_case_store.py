import time

import core.case_store as cs


def test_memory_store_roundtrip():
    store = cs.MemoryCaseStore()
    store.put("a", {"utterances": ["x"]})
    assert store.get("a") == {"utterances": ["x"]}
    assert store.exists("a")
    assert store.get("missing") is None


def test_memory_store_ttl(monkeypatch):
    monkeypatch.setattr(cs, "CASE_TTL_SECONDS", 0)
    store = cs.MemoryCaseStore()
    store.put("a", {"utterances": []})
    time.sleep(0.01)
    assert store.get("a") is None


def test_memory_store_cap(monkeypatch):
    monkeypatch.setattr(cs, "MAX_MEMORY_CASES", 3)
    store = cs.MemoryCaseStore()
    for i in range(6):
        store.put(f"case{i}", {"n": i})
        time.sleep(0.002)  # distinct expiry ordering
    alive = [f"case{i}" for i in range(6) if store.exists(f"case{i}")]
    assert len(alive) <= 3
    assert "case5" in alive, "newest case must survive the cap"
