"""Webhook HMAC and demo story smoke tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os

os.environ["DEMO_TIME_SCALE"] = "100000"

from fastapi.testclient import TestClient

from recoverpilot.integrations.razorpay_webhooks import build_sample_payment_failed, verify_signature
from recoverpilot.services.demo_story import CANONICAL_EVAL, demo_story


def test_verify_signature_accepts_valid():
    body = b'{"event":"payment.failed"}'
    secret = "whsec_test_secret"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig, secret) is True


def test_verify_signature_rejects_invalid():
    body = b'{"event":"payment.failed"}'
    assert verify_signature(body, "deadbeef", "whsec_test_secret") is False
    assert verify_signature(body, None, "whsec_test_secret") is False


def test_webhook_rejects_bad_signature_when_secret_set(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_forced_for_test")
    # Re-import config binding used by API — patch module attribute
    import recoverpilot.api.main as main_mod
    import recoverpilot.core.config as cfg

    monkeypatch.setattr(cfg, "RAZORPAY_WEBHOOK_SECRET", "whsec_forced_for_test")
    monkeypatch.setattr(main_mod, "RAZORPAY_WEBHOOK_SECRET", "whsec_forced_for_test")

    from recoverpilot.core import db

    db.get_engine()
    db.seed_demo_merchant()

    client = TestClient(main_mod.app)
    payload = build_sample_payment_failed(
        payment_id="pay_hmac_bad",
        amount_inr=100,
        decline_code="INSUFFICIENT_FUNDS",
        event_id="evt_hmac_bad",
    )
    body = json.dumps(payload).encode("utf-8")
    r = client.post(
        "/webhooks/razorpay",
        content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "not-valid"},
    )
    assert r.status_code == 401


def test_webhook_accepts_valid_signature_when_secret_set(monkeypatch):
    secret = "whsec_forced_for_test_ok"
    import recoverpilot.api.main as main_mod
    import recoverpilot.core.config as cfg

    monkeypatch.setattr(cfg, "RAZORPAY_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(main_mod, "RAZORPAY_WEBHOOK_SECRET", secret)

    from recoverpilot.core import db

    db.get_engine()
    db.seed_demo_merchant()

    client = TestClient(main_mod.app)
    payload = build_sample_payment_failed(
        payment_id="pay_hmac_ok",
        amount_inr=220,
        decline_code="ISSUER_TIMEOUT",
        event_id="evt_hmac_ok",
    )
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/webhooks/razorpay",
        content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("duplicate") is False or data.get("status") in {"accepted", "duplicate"}


def test_demo_story_has_proof():
    story = demo_story()
    assert story["proof"]["relative_lift_pct"] == CANONICAL_EVAL["relative_lift_pct"]
    assert story["proof"]["hard_decline_block_rate_pct"] == 100.0
    assert len(story["steps"]) >= 4
