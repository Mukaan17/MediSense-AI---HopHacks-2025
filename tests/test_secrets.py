"""Secret resolution: AWS SM (moto) -> env -> file -> default, plus
environment hydration."""

import pytest

from core import secrets


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    secrets.reset_cache_for_tests()
    monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    monkeypatch.delenv("SECRETS_PREFIX", raising=False)
    yield
    secrets.reset_cache_for_tests()


def test_env_wins_without_aws_backend(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "from-env")
    assert secrets.get_secret("MY_TOKEN") == "from-env"


def test_file_fallback(monkeypatch, tmp_path):
    p = tmp_path / "token"
    p.write_text("from-file\n")
    monkeypatch.delenv("MY_TOKEN", raising=False)
    monkeypatch.setenv("MY_TOKEN_FILE", str(p))
    assert secrets.get_secret("MY_TOKEN") == "from-file"


def test_default_when_nothing_set(monkeypatch):
    monkeypatch.delenv("MY_TOKEN", raising=False)
    monkeypatch.delenv("MY_TOKEN_FILE", raising=False)
    assert secrets.get_secret("MY_TOKEN", "fallback") == "fallback"


def test_aws_backend_wins_and_caches(monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from moto import mock_aws

    with mock_aws():
        client = boto3.client("secretsmanager", region_name="us-east-1")
        client.create_secret(Name="medisense/MY_TOKEN", SecretString="from-aws")

        monkeypatch.setenv("SECRETS_BACKEND", "aws")
        monkeypatch.setenv("SECRETS_PREFIX", "medisense/")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("MY_TOKEN", "from-env")  # AWS still wins

        assert secrets.get_secret("MY_TOKEN") == "from-aws"
        # Cached: a second call must not need the (now closed) mock.
    assert secrets.get_secret("MY_TOKEN") == "from-aws"


def test_aws_failure_falls_through_to_env(monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", "aws")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("MY_TOKEN", "from-env")
    # No moto mock and no real credentials: the AWS path fails, env serves.
    assert secrets.get_secret("MY_TOKEN") == "from-env"


def test_hydrate_environment(monkeypatch, tmp_path):
    p = tmp_path / "dsn"
    p.write_text("https://key@sentry.example/1")
    monkeypatch.delenv("HYDRATE_ME", raising=False)
    monkeypatch.setenv("HYDRATE_ME_FILE", str(p))
    secrets.hydrate_environment(["HYDRATE_ME"])
    import os
    assert os.environ["HYDRATE_ME"] == "https://key@sentry.example/1"
    monkeypatch.delenv("HYDRATE_ME", raising=False)


def test_auth_secret_resolves_via_file(monkeypatch, tmp_path):
    from core.auth import _get_secret
    p = tmp_path / "auth"
    p.write_text("k" * 64)
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    monkeypatch.setenv("AUTH_SECRET_KEY_FILE", str(p))
    assert _get_secret() == "k" * 64
