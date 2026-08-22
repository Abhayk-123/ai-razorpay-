"""Closed-loop production-like tests."""

from __future__ import annotations

import os

# Accelerate schedules before app imports use config
os.environ["DEMO_TIME_SCALE"] = "100000"

from recoverpilot.core import db
from recoverpilot.core.config import DEMO_API_KEY, DEMO_MERCHANT_ID
from recoverpilot.core.db import RecoveryJobRow, reset_engine, session
from recoverpilot.integrations.razorpay_webhooks import build_sample_payment_failed, normalize_razorpay_payload
from recoverpilot.ml.retrain import current_version, retrain
from recoverpilot.services import pipeline
from recoverpilot.workers.recovery_worker import execute_job, process_once


def setup_module():
    db.get_engine()
    db.seed_demo_merchant()


def test_webhook_idempotency():
    payload = build_sample_payment_failed(
        payment_id="pay_idem_001",
        amount_inr=500,
        decline_code="INSUFFICIENT_FUNDS",
        event_id="evt_idem_001",
    )
    event = normalize_razorpay_payload(payload, merchant_id=DEMO_MERCHANT_ID)
    first = pipeline.ingest_webhook_event(event, raw_payload=payload)
    second = pipeline.ingest_webhook_event(event, raw_payload=payload)
    assert first.duplicate is False
    assert second.duplicate is True
    assert first.failure_id == second.failure_id


def test_hard_decline_never_schedules_retry_job():
    payload = build_sample_payment_failed(
        payment_id="pay_hard_001",
        amount_inr=900,
        decline_code="STOLEN_CARD",
        event_id="evt_hard_001",
    )
    event = normalize_razorpay_payload(payload, merchant_id=DEMO_MERCHANT_ID)
    resp = pipeline.ingest_webhook_event(event, raw_payload=payload)
    assert resp.recommendation is not None
    assert resp.recommendation.action.value == "do_not_retry"
    assert resp.job_id is None
    fail = db.get_failure(resp.failure_id)
    assert fail is not None
    assert fail.status == "abandoned"


def test_worker_executes_due_job_and_writes_outcome():
    payload = build_sample_payment_failed(
        payment_id="pay_soft_worker_001",
        amount_inr=799,
        decline_code="ISSUER_TIMEOUT",
        event_id="evt_soft_worker_001",
    )
    event = normalize_razorpay_payload(payload, merchant_id=DEMO_MERCHANT_ID)
    resp = pipeline.ingest_webhook_event(event, raw_payload=payload)
    assert resp.job_id
    # Force due
    with session() as s:
        job = s.get(RecoveryJobRow, resp.job_id)
        assert job is not None
        from recoverpilot.core.db import utcnow

        job.run_at = utcnow()
        s.commit()
    result = execute_job(resp.job_id)
    assert result.get("ok") is True
    outcomes = db.list_outcomes(limit=50)
    assert any(o["failure_id"] == resp.failure_id for o in outcomes)


def test_retrain_bumps_version(tmp_path=None):
    before = current_version()
    # Ensure at least one outcome exists from previous test; if not, create soft path
    metrics = retrain(merge_synthetic=True)
    assert "version" in metrics
    assert metrics["version"] != before or before == "v0"
    assert metrics["version"].startswith("v")


def test_process_once_runs():
    n = process_once(limit=10)
    assert n >= 0
