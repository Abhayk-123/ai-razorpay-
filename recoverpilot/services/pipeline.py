"""Closed-loop pipeline: persist failure → recommend → enqueue recovery job."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from recoverpilot.agent.recovery_agent import build_explanation, decide_recovery_action
from recoverpilot.core import db
from recoverpilot.core.config import DEMO_TIME_SCALE
from recoverpilot.core.db import (
    PaymentFailureRow,
    RecommendationRow,
    RecoveryJobRow,
    failure_to_dict,
    new_id,
    session,
    utcnow,
    write_audit,
)
from recoverpilot.core.schemas import (
    FailureStatus,
    JobStatus,
    PaymentFailureEvent,
    RecommendResponse,
    RecoveryAction,
    WebhookIngestResponse,
)
from recoverpilot.ml.scorer import approximate_contributions, score_event


def _event_from_failure(row: PaymentFailureRow) -> PaymentFailureEvent:
    return PaymentFailureEvent(
        event_id=row.id,
        merchant_id=row.merchant_id,
        customer_id=row.customer_id,
        amount_inr=row.amount_inr,
        payment_method=row.payment_method,
        issuer_bucket=row.issuer_bucket,
        decline_code=row.decline_code,
        attempt_number=row.attempt_number,
        hour_of_day=row.hour_of_day,
        day_of_week=row.day_of_week,
        merchant_category=row.merchant_category,
        customer_tenure_days=row.customer_tenure_days,
        is_subscription=row.is_subscription,
        external_payment_id=row.external_payment_id,
        webhook_event_id=row.webhook_event_id,
    )


def scaled_delay_hours(hours: Optional[float]) -> float:
    h = float(hours or 0)
    if DEMO_TIME_SCALE and DEMO_TIME_SCALE > 1:
        return max(h / DEMO_TIME_SCALE, 0.01)
    return max(h, 0.0)


def create_job_for_recommendation(
    failure_id: str,
    action: RecoveryAction,
    retry_after_hours: Optional[float],
    channel: Optional[str],
    extra: dict[str, Any] | None = None,
) -> Optional[str]:
    """Create a recovery job when action requires execution. Returns job_id or None."""
    if action == RecoveryAction.DO_NOT_RETRY:
        with session() as s:
            row = s.get(PaymentFailureRow, failure_id)
            if row:
                row.status = FailureStatus.ABANDONED.value
                row.updated_at = utcnow()
                s.commit()
        return None

    if action == RecoveryAction.ESCALATE_MANUAL:
        delay_h = 0.0
    else:
        delay_h = scaled_delay_hours(retry_after_hours if action == RecoveryAction.SCHEDULE_RETRY else (retry_after_hours or 1))

    run_at = utcnow() + timedelta(hours=delay_h)
    job_id = new_id("job")
    with session() as s:
        s.add(
            RecoveryJobRow(
                id=job_id,
                failure_id=failure_id,
                action=action.value,
                run_at=run_at,
                status=JobStatus.PENDING.value,
                attempts=0,
                channel=channel,
                payload_json=json.dumps(extra or {}),
            )
        )
        fail = s.get(PaymentFailureRow, failure_id)
        if fail:
            fail.status = FailureStatus.SCHEDULED.value
            fail.updated_at = utcnow()
        s.commit()
    write_audit("system", "job_created", "recovery_job", job_id, {"failure_id": failure_id, "action": action.value})
    return job_id


def persist_and_recommend(event: PaymentFailureEvent, raw_payload: dict[str, Any] | None = None) -> RecommendResponse:
    """Upsert failure row, score, recommend, persist recommendation, enqueue job."""
    failure_id = event.event_id
    with session() as s:
        existing = s.get(PaymentFailureRow, failure_id)
        if existing is None:
            s.add(
                PaymentFailureRow(
                    id=failure_id,
                    merchant_id=event.merchant_id,
                    external_payment_id=event.external_payment_id or failure_id,
                    webhook_event_id=event.webhook_event_id,
                    customer_id=event.customer_id,
                    amount_inr=event.amount_inr,
                    payment_method=event.payment_method,
                    issuer_bucket=event.issuer_bucket,
                    decline_code=event.decline_code,
                    attempt_number=event.attempt_number,
                    hour_of_day=event.hour_of_day,
                    day_of_week=event.day_of_week,
                    merchant_category=event.merchant_category,
                    customer_tenure_days=event.customer_tenure_days,
                    is_subscription=event.is_subscription,
                    status=FailureStatus.OPEN.value,
                    raw_payload_json=json.dumps(raw_payload or event.model_dump(mode="json")),
                )
            )
            s.commit()

    payload = event.model_dump(mode="json")
    # Ensure scorer sees event_id key consistency
    payload["event_id"] = failure_id
    scored = score_event(payload)
    decision = decide_recovery_action(
        payload,
        scored["p_recovery"],
        scored["expected_value_inr"],
        scored["is_hard_decline"],
    )
    contribs = approximate_contributions(payload)
    explanation = build_explanation(
        payload,
        scored["p_recovery"],
        scored["expected_value_inr"],
        decision,
        contribs,
    )
    action = decision["action"]
    if not isinstance(action, RecoveryAction):
        action = RecoveryAction(action)

    with session() as s:
        s.add(
            RecommendationRow(
                failure_id=failure_id,
                p_recovery=scored["p_recovery"],
                expected_value_inr=scored["expected_value_inr"],
                action=action.value,
                retry_after_hours=decision.get("retry_after_hours"),
                channel=decision.get("channel"),
                playbook_id=decision["playbook_id"],
                playbook_excerpt=decision.get("playbook_excerpt", ""),
                explanation=explanation,
                feature_contributions_json=json.dumps(contribs),
                policy_notes_json=json.dumps(decision.get("policy_notes", [])),
                model_version=scored["model_version"],
            )
        )
        s.commit()

    job_id = create_job_for_recommendation(
        failure_id=failure_id,
        action=action,
        retry_after_hours=decision.get("retry_after_hours"),
        channel=decision.get("channel"),
        extra={"playbook_id": decision["playbook_id"]},
    )

    # legacy mirrors
    db.upsert_event(failure_id, payload)
    db.save_score(
        event_id=failure_id,
        p_recovery=scored["p_recovery"],
        expected_value_inr=scored["expected_value_inr"],
        is_hard_decline=scored["is_hard_decline"],
        model_version=scored["model_version"],
    )

    resp = RecommendResponse(
        event_id=failure_id,
        p_recovery=scored["p_recovery"],
        expected_value_inr=scored["expected_value_inr"],
        action=action,
        retry_after_hours=decision.get("retry_after_hours"),
        channel=decision.get("channel"),
        playbook_id=decision["playbook_id"],
        playbook_excerpt=decision.get("playbook_excerpt", ""),
        explanation=explanation,
        feature_contributions=contribs,
        policy_notes=decision.get("policy_notes", []),
        job_id=job_id,
    )
    db.save_action(failure_id, resp.action.value, resp.model_dump(mode="json"))
    return resp


def ingest_webhook_event(
    event: PaymentFailureEvent,
    raw_payload: dict[str, Any],
) -> WebhookIngestResponse:
    """Idempotent webhook ingest."""
    if event.webhook_event_id:
        existing = db.find_failure_by_webhook_event(event.webhook_event_id)
        if existing:
            return WebhookIngestResponse(
                status="duplicate",
                failure_id=existing.id,
                duplicate=True,
            )
    if event.external_payment_id:
        existing_pay = db.find_failure_by_external_payment(event.external_payment_id)
        if existing_pay:
            return WebhookIngestResponse(
                status="duplicate",
                failure_id=existing_pay.id,
                duplicate=True,
            )

    # Prefer stable failure id from payment id
    if event.external_payment_id:
        event.event_id = f"fail_{event.external_payment_id}"

    rec = persist_and_recommend(event, raw_payload=raw_payload)
    write_audit("webhook", "ingested", "payment_failure", rec.event_id, {"action": rec.action.value})
    return WebhookIngestResponse(
        status="accepted",
        failure_id=rec.event_id,
        duplicate=False,
        recommendation=rec,
        job_id=rec.job_id,
    )


def get_kpis() -> dict[str, Any]:
    from sqlalchemy import func, select

    from recoverpilot.core.db import OutcomeRow, RecoveryJobRow

    with session() as s:
        failures_total = s.scalar(select(func.count()).select_from(PaymentFailureRow)) or 0
        recovered_count = (
            s.scalar(select(func.count()).select_from(PaymentFailureRow).where(PaymentFailureRow.status == "recovered"))
            or 0
        )
        abandoned_count = (
            s.scalar(select(func.count()).select_from(PaymentFailureRow).where(PaymentFailureRow.status == "abandoned"))
            or 0
        )
        pending_jobs = (
            s.scalar(select(func.count()).select_from(RecoveryJobRow).where(RecoveryJobRow.status == "pending")) or 0
        )
        recovered_amount = s.scalar(select(func.coalesce(func.sum(OutcomeRow.recovered_amount), 0.0))) or 0.0
    rate = float(recovered_count) / float(failures_total) if failures_total else 0.0
    return {
        "failures_total": int(failures_total),
        "recovered_count": int(recovered_count),
        "abandoned_count": int(abandoned_count),
        "pending_jobs": int(pending_jobs),
        "recovered_amount_inr": round(float(recovered_amount), 2),
        "recovery_rate": round(rate, 4),
    }
