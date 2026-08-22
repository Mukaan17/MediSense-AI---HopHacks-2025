from core.evidence_engine import build_evidence
from core.fusion import fuse


def test_fuse_combines_image_and_text():
    image = [{"label": "Pneumonia", "score": 0.9}]
    text = [{"label": "pneumonia_unspecified"}]
    ranked = fuse(image, text, topk=10)
    assert ranked, "fusion produced no candidates"
    assert ranked[0]["score"] > 0.5
    conditions = [r["condition"] for r in ranked]
    assert any("pneumonia" in c for c in conditions)


def test_fuse_topk_bound():
    text = [{"label": f"condition_{i}"} for i in range(20)]
    assert len(fuse([], text, topk=5)) == 5


def test_evidence_fever_boosts_pneumonia():
    fused = [{"condition": "pneumonia_unspecified", "score": 0.55},
             {"condition": "upper_respiratory_infection", "score": 0.50}]
    ehr = {"vital_signs": {"temp_f": 101.5, "spo2_pct": 92}}
    out = build_evidence(image_findings=[], text_findings=[], ehr=ehr,
                         extracted={}, fused_ranked=fused, topk=10)
    shift = out.get("posterior_shift") or {}
    adjusted = {r["condition"]: r["score"] for r in shift.get("adjusted_top10", [])}
    assert adjusted.get("pneumonia_unspecified", 0) > 0.55, "fever/SpO2 should boost pneumonia"
    assert shift.get("shift_reasons"), "shift reasons must be present for explainability"


def test_evidence_no_signals_no_crash():
    out = build_evidence(image_findings=[], text_findings=[], ehr=None,
                         extracted={}, fused_ranked=[], topk=10)
    assert "posterior_shift" in out
