# -*- coding: utf-8 -*-
"""Live-case state store.

Cases were a module-level dict: lost on restart, invisible to sibling
workers, unbounded. This store keeps the same dict-shaped cases but behind
an interface with two backends:

- RedisCaseStore (REDIS_URL set): shared across workers and ECS tasks,
  TTL-expired server-side. Requires the `redis` package.
- MemoryCaseStore (default): per-process with TTL + size cap - correct for
  single-worker dev/demo, and the documented fallback when Redis is absent.

Cases must stay JSON-serializable (they already are: strings, numbers,
lists, dicts).
"""

import json
import os
import threading
import time
from typing import Any, Dict, Optional

CASE_TTL_SECONDS = int(os.getenv("CASE_TTL_SECONDS", "3600"))
MAX_MEMORY_CASES = int(os.getenv("MAX_MEMORY_CASES", "500"))


class MemoryCaseStore:
    backend = "memory"

    def __init__(self):
        self._cases: Dict[str, Dict[str, Any]] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [k for k, exp in self._expiry.items() if exp < now]
        for k in expired:
            self._cases.pop(k, None)
            self._expiry.pop(k, None)
        while len(self._cases) > MAX_MEMORY_CASES:
            oldest = min(self._expiry, key=self._expiry.get)
            self._cases.pop(oldest, None)
            self._expiry.pop(oldest, None)

    def get(self, case_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._evict()
            return self._cases.get(case_id)

    def put(self, case_id: str, case: Dict[str, Any]) -> None:
        with self._lock:
            self._cases[case_id] = case
            self._expiry[case_id] = time.monotonic() + CASE_TTL_SECONDS
            self._evict()

    def exists(self, case_id: str) -> bool:
        return self.get(case_id) is not None


class RedisCaseStore:
    backend = "redis"

    def __init__(self, url: str):
        import redis
        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._redis.ping()

    @staticmethod
    def _key(case_id: str) -> str:
        return f"medisense:case:{case_id}"

    def get(self, case_id: str) -> Optional[Dict[str, Any]]:
        raw = self._redis.get(self._key(case_id))
        return json.loads(raw) if raw else None

    def put(self, case_id: str, case: Dict[str, Any]) -> None:
        self._redis.set(self._key(case_id), json.dumps(case, ensure_ascii=False),
                        ex=CASE_TTL_SECONDS)

    def exists(self, case_id: str) -> bool:
        return bool(self._redis.exists(self._key(case_id)))


def make_case_store():
    url = os.getenv("REDIS_URL", "").strip()
    inner = None
    if url:
        try:
            inner = RedisCaseStore(url)
            print(f"[CASES] Redis case store connected: {url.split('@')[-1]}")
        except Exception as e:
            print(f"[CASES] Redis unavailable ({e}); falling back to in-memory store")
    if inner is None:
        inner = MemoryCaseStore()

    # Durable layer (approved decision D3): CASE_DB_URL adds an auditable
    # SQL timeline + snapshots over the fast store; absent, behavior is
    # unchanged.
    db_url = os.getenv("CASE_DB_URL", "").strip()
    if db_url:
        try:
            from core.persistence import DatabaseCaseStore
            store = DatabaseCaseStore(inner, db_url)
            print(f"[CASES] durable case store enabled ({store.backend})")
            return store
        except Exception as e:
            print(f"[CASES] durable store unavailable ({e}); continuing with {inner.backend}")
    return inner
