"""FHIR connector, verified against stubbed transport: SMART Backend
Services auth (RS384 JWT assertion), R4 -> internal EHR mapping,
DocumentReference write-back, and the EHR_SOURCE=fhir loader."""

import base64
import json

import pytest

pytest.importorskip("cryptography")

from core.fhir.client import FHIRClient
from core.fhir.mapping import ehr_record_from_bundles


@pytest.fixture(scope="module")
def rsa_key(tmp_path_factory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    path = tmp_path_factory.mktemp("fhir") / "key.pem"
    path.write_bytes(pem)
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return {"path": str(path), "public_pem": public_pem.decode()}


PATIENT = {"resourceType": "Patient", "id": "pat-1", "gender": "female",
           "birthDate": "1961-03-04"}
CONDITIONS = [
    {"resourceType": "Condition",
     "clinicalStatus": {"coding": [{"code": "active"}]},
     "code": {"text": "Type 2 diabetes mellitus"}},
    {"resourceType": "Condition",
     "clinicalStatus": {"coding": [{"code": "resolved"}]},
     "code": {"text": "Pneumonia (resolved)"}},
]
OBSERVATIONS = [
    {"resourceType": "Observation",
     "code": {"coding": [{"code": "85354-9"}]},
     "component": [
         {"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 136}},
         {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 78}},
     ]},
    {"resourceType": "Observation",
     "code": {"coding": [{"code": "8867-4"}]}, "valueQuantity": {"value": 92}},
    {"resourceType": "Observation",
     "code": {"coding": [{"code": "8310-5"}]},
     "valueQuantity": {"value": 38.1, "unit": "Cel"}},
    {"resourceType": "Observation",
     "code": {"coding": [{"code": "59408-5"}]}, "valueQuantity": {"value": 94}},
]
MEDS = [{"resourceType": "MedicationRequest",
         "medicationCodeableConcept": {"text": "Metformin 500 mg"}}]
ALLERGIES = [{"resourceType": "AllergyIntolerance", "code": {"text": "Penicillin"}}]


def test_mapping_produces_internal_record():
    rec = ehr_record_from_bundles(PATIENT, CONDITIONS, OBSERVATIONS, MEDS, ALLERGIES)
    assert rec["patient_id"] == "pat-1"
    assert rec["sex"] == "F"
    assert isinstance(rec["age"], int) and rec["age"] >= 60
    assert rec["vital_signs"]["bp"] == "136/78"
    assert rec["vital_signs"]["hr"] == 92.0
    assert rec["vital_signs"]["temp_f"] == pytest.approx(100.6, abs=0.1)
    assert rec["vital_signs"]["spo2_pct"] == 94.0
    # Resolved conditions are excluded from PMH.
    assert rec["pmh"] == ["Type 2 diabetes mellitus"]
    assert rec["meds"] == ["Metformin 500 mg"]
    assert rec["allergies"] == ["Penicillin"]
    assert rec["ehr_source"] == "fhir"


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _stub_transport(monkeypatch, rsa_key, captured):
    """Stub requests.get/post for the SMART + FHIR endpoints."""
    from core.fhir import client as client_mod

    def fake_get(url, **kwargs):
        captured.setdefault("gets", []).append((url, kwargs))
        if url.endswith("/.well-known/smart-configuration"):
            return _Resp({"token_endpoint": "https://auth.example/token"})
        if "/Patient/pat-1" in url:
            return _Resp(PATIENT)
        for name, items in (("Condition", CONDITIONS), ("Observation", OBSERVATIONS),
                            ("MedicationRequest", MEDS), ("AllergyIntolerance", ALLERGIES)):
            if url.endswith(f"/{name}"):
                return _Resp({"resourceType": "Bundle",
                              "entry": [{"resource": r} for r in items]})
        return _Resp({}, status=404)

    def fake_post(url, **kwargs):
        captured.setdefault("posts", []).append((url, kwargs))
        if url == "https://auth.example/token":
            # Verify the client assertion is a valid RS384 JWT for our key.
            from jose import jwt
            assertion = kwargs["data"]["client_assertion"]
            claims = jwt.decode(assertion, rsa_key["public_pem"],
                                algorithms=["RS384"], audience="https://auth.example/token")
            captured["assertion_claims"] = claims
            return _Resp({"access_token": "tok-123", "expires_in": 300})
        if url.endswith("/DocumentReference"):
            captured["docref"] = json.loads(kwargs["data"])
            return _Resp({"resourceType": "DocumentReference", "id": "doc-1"})
        return _Resp({}, status=404)

    monkeypatch.setattr(client_mod.requests, "get", fake_get)
    monkeypatch.setattr(client_mod.requests, "post", fake_post)


def test_smart_auth_and_reads(monkeypatch, rsa_key):
    captured = {}
    _stub_transport(monkeypatch, rsa_key, captured)
    c = FHIRClient(base_url="https://fhir.example/R4", client_id="medisense-client",
                   private_key_path=rsa_key["path"])
    patient = c.patient("pat-1")
    assert patient["id"] == "pat-1"
    # Assertion carried the SMART Backend Services claims.
    claims = captured["assertion_claims"]
    assert claims["iss"] == claims["sub"] == "medisense-client"
    assert claims["aud"] == "https://auth.example/token"
    # Bearer token used on the resource request.
    resource_gets = [k for (u, k) in captured["gets"] if "/Patient/" in u]
    assert resource_gets[0]["headers"]["Authorization"] == "Bearer tok-123"
    # Token is cached across calls: one token POST for many reads.
    c.conditions("pat-1")
    c.observations("pat-1")
    token_posts = [u for (u, _k) in captured["posts"] if u.endswith("/token")]
    assert len(token_posts) == 1


def test_document_reference_write_back(monkeypatch, rsa_key):
    captured = {}
    _stub_transport(monkeypatch, rsa_key, captured)
    c = FHIRClient(base_url="https://fhir.example/R4", client_id="medisense-client",
                   private_key_path=rsa_key["path"])
    out = c.create_document_reference("pat-1", "Advisory report body.")
    assert out["id"] == "doc-1"
    doc = captured["docref"]
    assert doc["subject"]["reference"] == "Patient/pat-1"
    assert "not a diagnosis" in doc["description"]
    decoded = base64.b64decode(doc["content"][0]["attachment"]["data"]).decode()
    assert decoded == "Advisory report body."


def test_loader_populates_internal_records(monkeypatch, rsa_key):
    captured = {}
    _stub_transport(monkeypatch, rsa_key, captured)
    monkeypatch.setenv("EHR_SOURCE", "fhir")
    monkeypatch.setenv("FHIR_BASE_URL", "https://fhir.example/R4")
    monkeypatch.setenv("FHIR_CLIENT_ID", "medisense-client")
    monkeypatch.setenv("FHIR_PRIVATE_KEY_PATH", rsa_key["path"])
    monkeypatch.setenv("FHIR_PATIENT_IDS", "pat-1")

    from core.fhir import load_fhir_records
    records = load_fhir_records()
    assert len(records) == 1
    assert records[0]["patient_id"] == "pat-1"
    assert records[0]["vital_signs"]["bp"] == "136/78"


def test_fhir_source_is_not_synthetic(monkeypatch):
    from core.app_mode import ehr_is_synthetic
    monkeypatch.setenv("EHR_SOURCE", "fhir")
    assert ehr_is_synthetic("ehr_with_images.json") is False
    monkeypatch.setenv("EHR_SOURCE", "file")
    assert ehr_is_synthetic("ehr_with_images.json") is True
