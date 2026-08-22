# -*- coding: utf-8 -*-
"""FHIR R4 client with SMART Backend Services auth (RFC 7523 JWT
assertion, RS384 per the SMART spec). Tokens are cached until near
expiry; every request carries the bearer token."""

import base64
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("core.fhir")

TOKEN_EARLY_REFRESH_S = 60


class FHIRClient:
    def __init__(self,
                 base_url: Optional[str] = None,
                 token_url: Optional[str] = None,
                 client_id: Optional[str] = None,
                 private_key_path: Optional[str] = None,
                 timeout_s: float = 15.0):
        self.base_url = (base_url or os.getenv("FHIR_BASE_URL", "")).rstrip("/")
        self.client_id = client_id or os.getenv("FHIR_CLIENT_ID", "")
        self.private_key_path = private_key_path or os.getenv("FHIR_PRIVATE_KEY_PATH", "")
        self._token_url = token_url or os.getenv("FHIR_TOKEN_URL", "")
        self.timeout_s = timeout_s
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    # ---- auth ----

    def _discover_token_url(self) -> str:
        if self._token_url:
            return self._token_url
        resp = requests.get(f"{self.base_url}/.well-known/smart-configuration",
                            timeout=self.timeout_s)
        resp.raise_for_status()
        self._token_url = resp.json()["token_endpoint"]
        return self._token_url

    def _client_assertion(self, token_url: str) -> str:
        """RFC 7523 JWT: iss=sub=client_id, aud=token endpoint, RS384."""
        from jose import jwt

        with open(self.private_key_path) as f:
            private_key = f.read()
        now = int(time.time())
        return jwt.encode(
            {"iss": self.client_id, "sub": self.client_id, "aud": token_url,
             "jti": str(uuid.uuid4()), "iat": now, "exp": now + 300},
            private_key, algorithm="RS384")

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - TOKEN_EARLY_REFRESH_S:
            return self._token
        token_url = self._discover_token_url()
        resp = requests.post(token_url, data={
            "grant_type": "client_credentials",
            "scope": os.getenv("FHIR_SCOPES", "system/Patient.rs system/Observation.rs "
                               "system/Condition.rs system/MedicationRequest.rs "
                               "system/AllergyIntolerance.rs system/DocumentReference.c"),
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": self._client_assertion(token_url),
        }, timeout=self.timeout_s)
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + float(body.get("expires_in", 300))
        return self._token

    # ---- reads ----

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=params or {},
            headers={"Authorization": f"Bearer {self._access_token()}",
                     "Accept": "application/fhir+json"},
            timeout=self.timeout_s)
        resp.raise_for_status()
        return resp.json()

    def patient(self, patient_id: str) -> Dict[str, Any]:
        return self._get(f"Patient/{patient_id}")

    def _search_all(self, resource: str, patient_id: str,
                    extra: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params = {"patient": patient_id, "_count": 100, **(extra or {})}
        bundle = self._get(resource, params)
        return [e.get("resource", {}) for e in bundle.get("entry", [])]

    def conditions(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._search_all("Condition", patient_id)

    def observations(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._search_all("Observation", patient_id,
                                {"category": "vital-signs", "_sort": "-date"})

    def medication_requests(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._search_all("MedicationRequest", patient_id, {"status": "active"})

    def allergies(self, patient_id: str) -> List[Dict[str, Any]]:
        return self._search_all("AllergyIntolerance", patient_id)

    # ---- write-back ----

    def create_document_reference(self, patient_id: str, report_text: str,
                                  title: str = "MediSense advisory report") -> Dict[str, Any]:
        """Write the advisory report back as a DocumentReference (plain text,
        clearly labeled advisory)."""
        doc = {
            "resourceType": "DocumentReference",
            "status": "current",
            "type": {"coding": [{"system": "http://loinc.org", "code": "11488-4",
                                 "display": "Consult note"}], "text": title},
            "subject": {"reference": f"Patient/{patient_id}"},
            "description": "Advisory reference only - not a diagnosis. Correlate clinically.",
            "content": [{"attachment": {
                "contentType": "text/plain",
                "data": base64.b64encode(report_text.encode("utf-8")).decode("ascii"),
                "title": title,
            }}],
        }
        resp = requests.post(
            f"{self.base_url}/DocumentReference",
            data=json.dumps(doc),
            headers={"Authorization": f"Bearer {self._access_token()}",
                     "Content-Type": "application/fhir+json"},
            timeout=self.timeout_s)
        resp.raise_for_status()
        return resp.json()
