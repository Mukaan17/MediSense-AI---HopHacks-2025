# -*- coding: utf-8 -*-
"""Durable case persistence (approved decision D3: relational, via
SQLAlchemy). The live case dict stays in the fast store (memory/Redis);
this package adds the auditable layer on top:

- an append-only event timeline per case (what the clinician was shown),
- durable case snapshots (cases survive restarts),
- stored reports,
- history queries and retention.

Enable with CASE_DB_URL (sqlite:///... for single-node, postgresql+psycopg://
in compose/prod). Without it, nothing here is imported at runtime.
"""

from .store import DatabaseCaseStore  # noqa: F401
