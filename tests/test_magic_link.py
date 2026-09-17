"""Magic-link portal: TTL, single-use, confirm recovers failure."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import timedelta

os.environ["DEMO_TIME_SCALE"] = "100000"

from sqlalchemy import select

from recoverpilot.core import db
from recoverpilot.core.config import DEMO_MERCHANT_ID
from recoverpilot.core.db import MagicLinkRow, session, utcnow
from recoverpilot.integrations.razorpay_webhooks import build_sample_payment_failed, normalize_razorpay_payload
from recoverpilot.services import pipeline
from recoverpilot.services.magic_link import confirm_magic_link, create_magic_link, inspect_magic_link


def setup_module():
    db.get_engine()
    db.seed_demo_merchant()


def _ingest(decline: str = "AUTHENTICATION_REQUIRED"):
    suffix = secrets.token_hex(3)
    payload = build_sample_payment_failed(
        payment_id=f"pay_magic_{suffix}",
        amount_inr=499,
        decline_code=decline,
        event_id=f"evt_magic_{suffix}",
    )
    event = normalize_razorpay_payload(payload, merchant_id=DEMO_MERCHANT_ID)
    return pipeline.ingest_webhook_event(event, raw_payload=payload)


def test_magic_link_confirm_recovers():
    resp = _ingest()
    assert resp.failure_id
    link = create_magic_link(resp.failure_id, 499.0, "AUTHENTICATION_REQUIRED")
    raw = link["token"]
    info = inspect_magic_link(raw)
    assert info["ok"] is True
    assert info["status"] == "active"

    result = confirm_magic_link(raw)
    assert result["ok"] is True
    assert result["status"] == "recovered"
    fail = db.get_failure(resp.failure_id)
    assert fail is not None
    assert fail.status == "recovered"

    again = confirm_magic_link(raw)
    assert again["ok"] is False


def test_magic_link_expiry():
    resp = _ingest()
    link = create_magic_link(resp.failure_id, 199.0, "AUTHENTICATION_REQUIRED")
    raw = link["token"]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with session() as s:
        row = s.scalars(select(MagicLinkRow).where(MagicLinkRow.token_hash == digest)).one()
        row.expires_at = utcnow() - timedelta(minutes=1)
        s.commit()

    info = inspect_magic_link(raw)
    assert info["ok"] is False
    assert info["status"] == "expired"
    result = confirm_magic_link(raw)
    assert result["ok"] is False
