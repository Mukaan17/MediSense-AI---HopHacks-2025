# -*- coding: utf-8 -*-
"""Secret resolution: AWS Secrets Manager -> environment -> file.

    SECRETS_BACKEND=aws          enables Secrets Manager lookups
    SECRETS_PREFIX=medisense/    secret id becomes f"{prefix}{name}"
    <NAME>                       plain environment variable
    <NAME>_FILE                  path to a file holding the value
                                 (docker/k8s secrets convention)

`hydrate_environment` copies resolved values into os.environ at startup so
code (and SDKs) that read plain env vars keep working unchanged. boto3 is
imported only when the aws backend is enabled - the default deployment
needs neither boto3 nor AWS credentials.
"""

import logging
import os
from typing import Dict, Iterable, Optional

log = logging.getLogger("core.secrets")

_sm_cache: Dict[str, Optional[str]] = {}


def _from_aws(name: str) -> Optional[str]:
    if os.getenv("SECRETS_BACKEND", "").strip().lower() != "aws":
        return None
    secret_id = f"{os.getenv('SECRETS_PREFIX', '')}{name}"
    if secret_id in _sm_cache:
        return _sm_cache[secret_id]
    try:
        import boto3
        client = boto3.client("secretsmanager",
                              region_name=os.getenv("AWS_REGION", "us-east-1"))
        value = client.get_secret_value(SecretId=secret_id).get("SecretString")
    except Exception as e:
        log.warning(f"[secrets] AWS lookup failed for {secret_id}: {e}")
        value = None
    _sm_cache[secret_id] = value
    return value


def _from_file(name: str) -> Optional[str]:
    path = os.getenv(f"{name}_FILE", "").strip()
    if not path:
        return None
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception as e:
        log.warning(f"[secrets] unreadable {name}_FILE={path}: {e}")
        return None


def get_secret(name: str, default: str = "") -> str:
    aws = _from_aws(name)
    if aws is not None:
        return aws
    env = os.getenv(name)
    if env:
        return env
    file_value = _from_file(name)
    if file_value is not None:
        return file_value
    return default


def hydrate_environment(names: Iterable[str]) -> None:
    """Resolve each name and export it as a plain env var when found, so
    SDKs that only read the environment (e.g. LLM clients) pick it up."""
    for name in names:
        if os.getenv(name):
            continue
        value = get_secret(name)
        if value:
            os.environ[name] = value
            log.info(f"[secrets] hydrated {name} from managed source")


def reset_cache_for_tests() -> None:
    _sm_cache.clear()
