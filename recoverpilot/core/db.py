"""SQLAlchemy domain models and persistence helpers."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from recoverpilot.core.config import (
    DATABASE_URL,
    DEMO_API_KEY,
    DEMO_MERCHANT_ID,
    DEMO_MERCHANT_NAME,
    DEMO_WEBHOOK_SECRET,
)
from recoverpilot.core.paths import ensure_dirs


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class Base(DeclarativeBase):
    pass


class MerchantRow(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    api_key_hash: Mapped[str] = mapped_column(String(128), index=True)
    webhook_secret: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(64), default="saas")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PaymentFailureRow(Base):
    __tablename__ = "payment_failures"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    external_payment_id: Mapped[str] = mapped_column(String(128), index=True)
    webhook_event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    customer_id: Mapped[str] = mapped_column(String(64))
    amount_inr: Mapped[float] = mapped_column(Float)
    payment_method: Mapped[str] = mapped_column(String(64))
    issuer_bucket: Mapped[str] = mapped_column(String(64))
    decline_code: Mapped[str] = mapped_column(String(64))
    attempt_number: Mapped[int] = mapped_column(Integer)
    hour_of_day: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)
    merchant_category: Mapped[str] = mapped_column(String(64))
    customer_tenure_days: Mapped[int] = mapped_column(Integer)
    is_subscription: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    raw_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecommendationRow(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    failure_id: Mapped[str] = mapped_column(String(64), index=True)
    p_recovery: Mapped[float] = mapped_column(Float)
    expected_value_inr: Mapped[float] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(64))
    retry_after_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    playbook_id: Mapped[str] = mapped_column(String(64))
    playbook_excerpt: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    feature_contributions_json: Mapped[str] = mapped_column(Text, default="{}")
    policy_notes_json: Mapped[str] = mapped_column(Text, default="[]")
    model_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecoveryJobRow(Base):
    __tablename__ = "recovery_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    run_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    channel: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JobExecutionRow(Base):
    __tablename__ = "job_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutcomeRow(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    failure_id: Mapped[str] = mapped_column(String(64), index=True)
    recovered: Mapped[bool] = mapped_column(Boolean)
    recovered_amount: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(32))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutboxRow(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    failure_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MagicLinkRow(Base):
    """Hashed single-use customer recovery tokens (never store raw token)."""

    __tablename__ = "magic_links"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_id: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    amount_inr: Mapped[float] = mapped_column(Float)
    decline_code: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLogRow(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(128))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# Legacy tables kept for backward compatibility with old demo endpoints
class EventRow(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ScoreRow(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    p_recovery: Mapped[float] = mapped_column(Float)
    expected_value_inr: Mapped[float] = mapped_column(Float)
    is_hard_decline: Mapped[bool] = mapped_column(Boolean)
    model_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ActionRow(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    recommendation_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OverrideRow(Base):
    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    operator: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        ensure_dirs()
        connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
        _engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def session() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def reset_engine() -> None:
    """Test helper to recreate engine after DB wipe."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def seed_demo_merchant() -> MerchantRow:
    get_engine()
    with session() as s:
        row = s.get(MerchantRow, DEMO_MERCHANT_ID)
        if row is None:
            row = MerchantRow(
                id=DEMO_MERCHANT_ID,
                name=DEMO_MERCHANT_NAME,
                api_key_hash=hash_api_key(DEMO_API_KEY),
                webhook_secret=DEMO_WEBHOOK_SECRET,
                category="saas",
            )
            s.add(row)
            s.commit()
            s.refresh(row)
        return row


def get_merchant_by_api_key(api_key: str) -> Optional[MerchantRow]:
    digest = hash_api_key(api_key)
    with session() as s:
        return s.scalars(select(MerchantRow).where(MerchantRow.api_key_hash == digest)).first()


def get_merchant(merchant_id: str) -> Optional[MerchantRow]:
    with session() as s:
        return s.get(MerchantRow, merchant_id)


def write_audit(actor: str, action: str, entity_type: str, entity_id: str, details: dict[str, Any] | None = None) -> None:
    with session() as s:
        s.add(
            AuditLogRow(
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details_json=json.dumps(details or {}),
            )
        )
        s.commit()


def failure_to_dict(row: PaymentFailureRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_id": row.id,
        "merchant_id": row.merchant_id,
        "external_payment_id": row.external_payment_id,
        "webhook_event_id": row.webhook_event_id,
        "customer_id": row.customer_id,
        "amount_inr": row.amount_inr,
        "payment_method": row.payment_method,
        "issuer_bucket": row.issuer_bucket,
        "decline_code": row.decline_code,
        "attempt_number": row.attempt_number,
        "hour_of_day": row.hour_of_day,
        "day_of_week": row.day_of_week,
        "merchant_category": row.merchant_category,
        "customer_tenure_days": row.customer_tenure_days,
        "is_subscription": row.is_subscription,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def job_to_dict(row: RecoveryJobRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "failure_id": row.failure_id,
        "action": row.action,
        "run_at": row.run_at.isoformat() if row.run_at else None,
        "status": row.status,
        "attempts": row.attempts,
        "channel": row.channel,
        "payload": json.loads(row.payload_json or "{}"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_failure(failure_id: str) -> Optional[PaymentFailureRow]:
    with session() as s:
        return s.get(PaymentFailureRow, failure_id)


def list_failures(limit: int = 100, status: Optional[str] = None, merchant_id: Optional[str] = None) -> list[dict[str, Any]]:
    with session() as s:
        q = select(PaymentFailureRow).order_by(PaymentFailureRow.created_at.desc()).limit(limit)
        if status:
            q = q.where(PaymentFailureRow.status == status)
        if merchant_id:
            q = q.where(PaymentFailureRow.merchant_id == merchant_id)
        rows = s.scalars(q).all()
        return [failure_to_dict(r) for r in rows]


def list_jobs(limit: int = 100, status: Optional[str] = None) -> list[dict[str, Any]]:
    with session() as s:
        q = select(RecoveryJobRow).order_by(RecoveryJobRow.run_at.asc()).limit(limit)
        if status:
            q = q.where(RecoveryJobRow.status == status)
        rows = s.scalars(q).all()
        return [job_to_dict(r) for r in rows]


def list_outcomes(limit: int = 200) -> list[dict[str, Any]]:
    with session() as s:
        rows = s.scalars(select(OutcomeRow).order_by(OutcomeRow.created_at.desc()).limit(limit)).all()
        return [
            {
                "id": r.id,
                "failure_id": r.failure_id,
                "recovered": r.recovered,
                "recovered_amount": r.recovered_amount,
                "source": r.source,
                "details": json.loads(r.details_json or "{}"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def find_failure_by_webhook_event(webhook_event_id: str) -> Optional[PaymentFailureRow]:
    with session() as s:
        return s.scalars(
            select(PaymentFailureRow).where(PaymentFailureRow.webhook_event_id == webhook_event_id)
        ).first()


def find_failure_by_external_payment(external_payment_id: str) -> Optional[PaymentFailureRow]:
    with session() as s:
        return s.scalars(
            select(PaymentFailureRow).where(PaymentFailureRow.external_payment_id == external_payment_id)
        ).first()


# ---- legacy helpers ----

def upsert_event(event_id: str, payload: dict[str, Any]) -> None:
    with session() as s:
        row = s.get(EventRow, event_id)
        if row is None:
            s.add(EventRow(event_id=event_id, payload_json=json.dumps(payload)))
        else:
            row.payload_json = json.dumps(payload)
        s.commit()


def save_score(
    event_id: str,
    p_recovery: float,
    expected_value_inr: float,
    is_hard_decline: bool,
    model_version: str,
) -> None:
    with session() as s:
        s.add(
            ScoreRow(
                event_id=event_id,
                p_recovery=p_recovery,
                expected_value_inr=expected_value_inr,
                is_hard_decline=is_hard_decline,
                model_version=model_version,
            )
        )
        s.commit()


def save_action(event_id: str, action: str, recommendation: dict[str, Any]) -> None:
    with session() as s:
        s.add(
            ActionRow(
                event_id=event_id,
                action=action,
                recommendation_json=json.dumps(recommendation),
            )
        )
        s.commit()


def save_override(event_id: str, action: str, reason: str, operator: str) -> None:
    with session() as s:
        s.add(
            OverrideRow(
                event_id=event_id,
                action=action,
                reason=reason,
                operator=operator,
            )
        )
        s.commit()


def list_recent_events(limit: int = 100) -> list[dict[str, Any]]:
    with session() as s:
        rows = s.scalars(select(EventRow).order_by(EventRow.created_at.desc()).limit(limit)).all()
        return [json.loads(r.payload_json) for r in rows]


def get_event(event_id: str) -> Optional[dict[str, Any]]:
    with session() as s:
        row = s.get(EventRow, event_id)
        return json.loads(row.payload_json) if row else None


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"
