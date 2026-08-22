# -*- coding: utf-8 -*-
"""DatabaseCaseStore: the fast store's interface plus a durable layer.

Reads hit the wrapped fast store first and fall back to the DB snapshot
(cases survive restarts and TTL eviction); writes go to both. Events and
reports are DB-only - they ARE the audit value."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Case, CaseEvent, Report

log = logging.getLogger("core.persistence")


class DatabaseCaseStore:
    def __init__(self, inner, url: str):
        self.inner = inner
        self.backend = f"database+{inner.backend}"
        self._engine = create_engine(url, future=True, pool_pre_ping=True)
        Base.metadata.create_all(self._engine)
        self._session: sessionmaker[Session] = sessionmaker(
            self._engine, expire_on_commit=False)

    # ---- fast-store interface ----

    def get(self, case_id: str) -> Optional[Dict[str, Any]]:
        case = self.inner.get(case_id)
        if case is not None:
            return case
        with self._session() as s:
            row = s.get(Case, case_id)
            if row is None:
                return None
            # Restart/eviction recovery: rehydrate the fast store.
            self.inner.put(case_id, row.state)
            return row.state

    def put(self, case_id: str, case: Dict[str, Any]) -> None:
        self.inner.put(case_id, case)
        try:
            with self._session() as s:
                row = s.get(Case, case_id)
                patient_id = ((case.get("ehr") or {}).get("patient_id")
                              if isinstance(case.get("ehr"), dict) else None)
                if row is None:
                    s.add(Case(id=case_id, state=case, patient_id=patient_id))
                else:
                    row.state = case
                    row.patient_id = patient_id or row.patient_id
                    row.updated_at = datetime.now(timezone.utc)
                s.commit()
        except Exception as e:
            # The live path must never die on the durable layer.
            log.warning(f"[persistence] snapshot write failed for {case_id}: {e}")

    def exists(self, case_id: str) -> bool:
        return self.get(case_id) is not None

    # ---- durable layer ----

    def append_event(self, case_id: str, type: str, payload: Dict[str, Any]) -> None:
        try:
            with self._session() as s:
                if s.get(Case, case_id) is None:
                    s.add(Case(id=case_id, state={}))
                s.add(CaseEvent(case_id=case_id, type=type, payload=payload))
                s.commit()
        except Exception as e:
            log.warning(f"[persistence] event write failed for {case_id}: {e}")

    def get_timeline(self, case_id: str) -> List[Dict[str, Any]]:
        with self._session() as s:
            rows = s.execute(
                select(CaseEvent).where(CaseEvent.case_id == case_id)
                .order_by(CaseEvent.ts, CaseEvent.id)).scalars().all()
            return [{"ts": r.ts.isoformat(), "type": r.type, "payload": r.payload}
                    for r in rows]

    def save_report(self, case_id: str, report: str, model: Optional[str],
                    fusion: Dict[str, Any]) -> None:
        try:
            with self._session() as s:
                if s.get(Case, case_id) is None:
                    s.add(Case(id=case_id, state={}))
                s.add(Report(case_id=case_id, report=report, model=model,
                             fusion=fusion or {}))
                s.commit()
        except Exception as e:
            log.warning(f"[persistence] report write failed for {case_id}: {e}")

    def list_cases(self, patient_id: Optional[str] = None,
                   limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self._session() as s:
            q = select(Case).order_by(Case.updated_at.desc())
            if patient_id:
                q = q.where(Case.patient_id == patient_id)
            rows = s.execute(q.limit(limit).offset(offset)).scalars().all()
            out = []
            for r in rows:
                state = r.state or {}
                out.append({
                    "case_id": r.id,
                    "patient_id": r.patient_id,
                    "created_at": r.created_at.isoformat(),
                    "updated_at": r.updated_at.isoformat(),
                    "utterance_count": len(state.get("utterances", []) or []),
                    "top_condition": ((state.get("ranked") or [{}])[0] or {}).get("condition"),
                })
            return out

    def purge_older_than(self, days: int) -> int:
        """Retention: delete cases (and cascading events/reports) whose last
        update is older than `days`. Returns rows removed."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._session() as s:
            ids = [r for (r,) in s.execute(
                select(Case.id).where(Case.updated_at < cutoff)).all()]
            if not ids:
                return 0
            # Explicit child deletes: ondelete=CASCADE needs FK enforcement,
            # which SQLite doesn't guarantee by default.
            s.execute(delete(CaseEvent).where(CaseEvent.case_id.in_(ids)))
            s.execute(delete(Report).where(Report.case_id.in_(ids)))
            s.execute(delete(Case).where(Case.id.in_(ids)))
            s.commit()
            return len(ids)
