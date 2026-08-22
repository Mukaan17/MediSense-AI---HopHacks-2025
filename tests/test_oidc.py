"""OIDC scaffolding against a stub IdP: PKCE authorization URL, signed
state, id_token validation (JWKS, iss/aud/nonce), role mapping, and the
callback issuing the app's own session cookies."""

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("cryptography")


@pytest.fixture(scope="module")
def idp(tmp_path_factory):
    """Stub IdP: RSA keypair + JWKS + canned discovery."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose import jwt
    from jose.utils import long_to_base64

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    numbers = key.public_key().public_numbers()
    jwks = {"keys": [{
        "kty": "RSA", "kid": "test-key", "use": "sig", "alg": "RS256",
        "n": long_to_base64(numbers.n).decode(),
        "e": long_to_base64(numbers.e).decode(),
    }]}

    def make_id_token(nonce: str, roles):
        now = int(time.time())
        return jwt.encode(
            {"iss": "https://idp.example/realms/hospital", "aud": "medisense",
             "sub": "u-123", "preferred_username": "dr.house",
             "email": "house@example.org", "nonce": nonce, "roles": roles,
             "iat": now, "exp": now + 300},
            private_pem, algorithm="RS256", headers={"kid": "test-key"})

    return {"jwks": jwks, "make_id_token": make_id_token}


@pytest.fixture()
def oidc_env(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("AUTH_SECRET_KEY", "s" * 64)
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example/realms/hospital")
    monkeypatch.setenv("OIDC_CLIENT_ID", "medisense")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example/auth/oidc/callback")
    monkeypatch.setenv("OIDC_ADMIN_ROLES", "medisense-admin")


def _stub_idp_transport(monkeypatch, idp, captured, roles):
    from core import oidc as oidc_mod

    oidc_mod._discovery_cache.clear()

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    def fake_get(url, **kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return _Resp({
                "authorization_endpoint": "https://idp.example/auth",
                "token_endpoint": "https://idp.example/token",
                "jwks_uri": "https://idp.example/jwks",
            })
        if url.endswith("/jwks"):
            return _Resp(idp["jwks"])
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, **kwargs):
        assert url == "https://idp.example/token"
        captured["token_request"] = kwargs["data"]
        nonce = captured["nonce"]
        return _Resp({"id_token": idp["make_id_token"](nonce, roles),
                      "access_token": "at", "token_type": "Bearer"})

    monkeypatch.setattr(oidc_mod.requests, "get", fake_get)
    monkeypatch.setattr(oidc_mod.requests, "post", fake_post)


def _start_flow(captured):
    """Build the auth URL and pull nonce/state/PKCE out of it."""
    from jose import jwt as jose_jwt
    from core.oidc import build_authorization_url

    url = build_authorization_url()
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    state_claims = jose_jwt.get_unverified_claims(q["state"])
    captured["nonce"] = state_claims["n"]
    return q


def test_authorization_url_carries_pkce_and_signed_state(oidc_env, monkeypatch, idp):
    captured = {}
    _stub_idp_transport(monkeypatch, idp, captured, roles=[])
    q = _start_flow(captured)
    assert q["response_type"] == "code"
    assert q["code_challenge_method"] == "S256"
    assert q["client_id"] == "medisense"
    # The state is OUR signed JWT carrying the PKCE verifier + nonce.
    from core.oidc import _decode_state
    payload = _decode_state(q["state"])
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(payload["v"].encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == expected


def test_exchange_validates_and_maps_roles(oidc_env, monkeypatch, idp):
    captured = {}
    _stub_idp_transport(monkeypatch, idp, captured, roles=["medisense-admin"])
    q = _start_flow(captured)
    from core.oidc import exchange_code
    user = exchange_code("auth-code-1", q["state"])
    assert user == {"username": "dr.house", "role": "admin"}
    # PKCE verifier travelled to the token endpoint.
    assert captured["token_request"]["code_verifier"]
    assert captured["token_request"]["code"] == "auth-code-1"


def test_exchange_maps_default_role(oidc_env, monkeypatch, idp):
    captured = {}
    _stub_idp_transport(monkeypatch, idp, captured, roles=["nurse"])
    q = _start_flow(captured)
    from core.oidc import exchange_code
    assert exchange_code("c", q["state"])["role"] == "clinician"


def test_exchange_rejects_nonce_mismatch(oidc_env, monkeypatch, idp):
    captured = {}
    _stub_idp_transport(monkeypatch, idp, captured, roles=[])
    q = _start_flow(captured)
    captured["nonce"] = "attacker-controlled"  # token minted for a different nonce
    from core.oidc import exchange_code
    with pytest.raises(RuntimeError, match="nonce"):
        exchange_code("c", q["state"])


def test_login_route_redirects_and_callback_sets_cookies(oidc_env, monkeypatch, idp, client):
    captured = {}
    _stub_idp_transport(monkeypatch, idp, captured, roles=[])
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")

    r = client.get("/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302
    q = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    from jose import jwt as jose_jwt
    captured["nonce"] = jose_jwt.get_unverified_claims(q["state"])["n"]

    cb = client.get(f"/auth/oidc/callback?code=abc&state={q['state']}",
                    follow_redirects=False)
    assert cb.status_code == 302
    assert "medisense_session" in cb.cookies
    assert "medisense_csrf" in cb.cookies


def test_oidc_routes_503_when_disabled(client, monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert client.get("/auth/oidc/login", follow_redirects=False).status_code == 503
