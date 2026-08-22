# -*- coding: utf-8 -*-
"""SQLAlchemy models: cases (snapshot), case_events (append-only),
reports. JSON columns keep the shapes the pipeline already uses."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)
    # Latest live-case dict; the timeline is the authoritative history.
    state: Mapped[dict] = mapped_column(JSON, default=dict)


class CaseEvent(Base):
    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_case_events_case_ts", "case_id", "ts"),)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    report: Mapped[str] = mapped_column(Text)
    fusion: Mapped[dict] = mapped_column(JSON, default=dict)
