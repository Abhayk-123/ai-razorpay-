"""Zero-login magic-link portal for dunning recovery (15-min TTL, single-use)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select

from recoverpilot.core.config import API_BASE_URL, PUBLIC_BASE_URL
from recoverpilot.core.db import (
    MagicLinkRow,
    OutcomeRow,
    PaymentFailureRow,
    new_id,
    session,
    utcnow,
    write_audit,
)
from recoverpilot.core.schemas import FailureStatus

MAGIC_LINK_TTL_MINUTES = 15


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_magic_link(failure_id: str, amount_inr: float, decline_code: str) -> dict[str, Any]:
    """Create a single-use magic link. Returns raw token once (never stored plaintext)."""
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    link_id = new_id("ml")
    expires = utcnow() + timedelta(minutes=MAGIC_LINK_TTL_MINUTES)
    base = (PUBLIC_BASE_URL or API_BASE_URL).rstrip("/")
    url = f"{base}/recover/{raw}"

    with session() as s:
        s.add(
            MagicLinkRow(
                id=link_id,
                failure_id=failure_id,
                token_hash=token_hash,
                amount_inr=float(amount_inr),
                decline_code=decline_code,
                expires_at=expires,
                used_at=None,
                status="active",
            )
        )
        s.commit()

    write_audit("system", "magic_link_created", "magic_link", link_id, {"failure_id": failure_id})
    return {
        "link_id": link_id,
        "token": raw,
        "url": url,
        "expires_at": expires.isoformat(),
        "ttl_minutes": MAGIC_LINK_TTL_MINUTES,
    }


def _get_by_raw_token(raw: str) -> Optional[MagicLinkRow]:
    digest = _hash_token(raw)
    with session() as s:
        return s.scalars(select(MagicLinkRow).where(MagicLinkRow.token_hash == digest)).first()


def inspect_magic_link(raw: str) -> dict[str, Any]:
    row = _get_by_raw_token(raw)
    if row is None:
        return {"ok": False, "error": "invalid_or_unknown", "status": "invalid"}
    now = utcnow()
    exp = row.expires_at
    if exp.tzinfo is None:
        from datetime import timezone

        exp = exp.replace(tzinfo=timezone.utc)
    expired = exp < now
    used = row.used_at is not None or row.status == "used"
    if used:
        status = "used"
    elif expired or row.status == "expired":
        status = "expired"
    else:
        status = "active"

    fail = None
    with session() as s:
        fail = s.get(PaymentFailureRow, row.failure_id)

    return {
        "ok": status == "active",
        "status": status,
        "failure_id": row.failure_id,
        "amount_inr": row.amount_inr,
        "decline_code": row.decline_code,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "customer_id": fail.customer_id if fail else None,
        "payment_method": fail.payment_method if fail else None,
        "last4_stub": "••••",
    }


def confirm_magic_link(raw: str) -> dict[str, Any]:
    """Customer confirms payment method update → mark recovered (demo)."""
    info = inspect_magic_link(raw)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("status", "invalid"), **info}

    digest = _hash_token(raw)
    with session() as s:
        row = s.scalars(select(MagicLinkRow).where(MagicLinkRow.token_hash == digest)).first()
        if row is None:
            return {"ok": False, "error": "invalid"}
        # Re-check inside transaction
        now = utcnow()
        exp = row.expires_at
        if exp.tzinfo is None:
            from datetime import timezone

            exp = exp.replace(tzinfo=timezone.utc)
        if row.used_at is not None or row.status == "used":
            return {"ok": False, "error": "used"}
        if exp < now:
            row.status = "expired"
            s.commit()
            return {"ok": False, "error": "expired"}

        row.used_at = now
        row.status = "used"
        fail = s.get(PaymentFailureRow, row.failure_id)
        amount = float(row.amount_inr)
        if fail:
            fail.status = FailureStatus.RECOVERED.value
            fail.updated_at = now
            amount = float(fail.amount_inr)
        s.add(
            OutcomeRow(
                failure_id=row.failure_id,
                recovered=True,
                recovered_amount=amount,
                source="magic_link",
                details_json='{"mode":"customer_portal_confirm"}',
            )
        )
        s.commit()
        failure_id = row.failure_id

    write_audit("customer", "magic_link_confirmed", "payment_failure", failure_id, {"source": "magic_link"})
    return {
        "ok": True,
        "status": "recovered",
        "failure_id": failure_id,
        "recovered_amount": amount,
        "message": "Payment method updated. Invoice marked recovered (demo).",
    }
