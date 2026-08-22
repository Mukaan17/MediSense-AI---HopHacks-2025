import importlib


def test_routing_matrix(monkeypatch):
    import core.llm_client as lc
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LIVE_MODEL", raising=False)
    monkeypatch.delenv("FINAL_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    assert lc.get_live_model().startswith("gemini")
    assert lc.get_final_model().startswith("gemini")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert lc.get_live_model().startswith("claude")
    assert lc.get_final_model().startswith("claude")

    monkeypatch.setenv("LIVE_MODEL", "claude-custom")
    assert lc.get_live_model() == "claude-custom"


def test_gemini_cache_keyed_on_temperature(monkeypatch):
    import core.llm_client as lc
    importlib.reload(lc)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    a = lc.get_llm(temperature=0.1)
    b = lc.get_llm(temperature=0.9)
    assert b.temperature == 0.9, "temperature change must produce a matching client"
    c = lc.get_llm(temperature=0.9)
    assert c is b, "same (model, temperature) must reuse the cached client"
