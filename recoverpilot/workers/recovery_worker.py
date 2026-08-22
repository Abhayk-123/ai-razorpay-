"""Background recovery worker: claim due jobs and execute recovery actions."""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

from recoverpilot.core.config import HARD_DECLINE_CODES, OUTBOX_DIR, WORKER_POLL_SECONDS
from recoverpilot.core.db import (
    JobExecutionRow,
    OutcomeRow,
    OutboxRow,
    PaymentFailureRow,
    RecoveryJobRow,
    get_engine,
    seed_demo_merchant,
    session,
    utcnow,
    write_audit,
)
from recoverpilot.core.paths import ensure_dirs
from recoverpilot.core.schemas import FailureStatus, JobStatus, RecoveryAction
from recoverpilot.ml.scorer import score_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("recoverpilot.worker")


def _failure_payload(row: PaymentFailureRow) -> dict[str, Any]:
    return {
        "event_id": row.id,
        "merchant_id": row.merchant_id,
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
    }


def claim_due_jobs(limit: int = 20) -> list[str]:
    now = utcnow()
    claimed: list[str] = []
    with session() as s:
        rows = s.scalars(
            select(RecoveryJobRow)
            .where(RecoveryJobRow.status == JobStatus.PENDING.value)
            .where(RecoveryJobRow.run_at <= now)
            .order_by(RecoveryJobRow.run_at.asc())
            .limit(limit)
        ).all()
        for row in rows:
            row.status = JobStatus.RUNNING.value
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = now
            claimed.append(row.id)
        s.commit()
    return claimed


def _simulate_retry_success(failure: PaymentFailureRow) -> bool:
    if failure.decline_code in HARD_DECLINE_CODES:
        return False
    scored = score_event(_failure_payload(failure))
    # Local simulated issuer response — not a real charge
    p = scored["p_recovery"]
    # Slight boost for auth dunning path handled separately
    return random.random() < max(0.05, min(0.92, p))


def _write_outbox_file(failure_id: str, channel: str, subject: str, body: str) -> Path:
    ensure_dirs()
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTBOX_DIR / f"{failure_id}_{int(time.time())}.txt"
    path.write_text(f"channel={channel}\nsubject={subject}\n\n{body}\n", encoding="utf-8")
    return path


def execute_job(job_id: str) -> dict[str, Any]:
    with session() as s:
        job = s.get(RecoveryJobRow, job_id)
        if job is None:
            return {"ok": False, "error": "job_not_found"}
        failure = s.get(PaymentFailureRow, job.failure_id)
        if failure is None:
            job.status = JobStatus.FAILED.value
            job.updated_at = utcnow()
            s.add(JobExecutionRow(job_id=job_id, result_json="{}", error="failure_not_found"))
            s.commit()
            return {"ok": False, "error": "failure_not_found"}

        action = job.action
        result: dict[str, Any] = {"action": action}
        try:
            if action == RecoveryAction.SCHEDULE_RETRY.value:
                ok = _simulate_retry_success(failure)
                result["recovered"] = ok
                result["mode"] = "simulated_retry"
                s.add(
                    OutcomeRow(
                        failure_id=failure.id,
                        recovered=ok,
                        recovered_amount=float(failure.amount_inr) if ok else 0.0,
                        source="retry",
                        details_json=json.dumps(result),
                    )
                )
                failure.status = FailureStatus.RECOVERED.value if ok else FailureStatus.EXECUTED.value
            elif action == RecoveryAction.SEND_DUNNING.value:
                subject = "Update your payment method"
                body = (
                    f"Hi customer {failure.customer_id},\n"
                    f"Your payment of ₹{failure.amount_inr:.2f} failed ({failure.decline_code}).\n"
                    f"Please update payment details to continue your subscription.\n"
                )
                channel = job.channel or "email_sms"
                path = _write_outbox_file(failure.id, channel, subject, body)
                s.add(
                    OutboxRow(
                        failure_id=failure.id,
                        channel=channel,
                        subject=subject,
                        body=body,
                        status="sent_stub",
                    )
                )
                # Dunning itself is not recovery; simulate modest reopen rate
                reopen = random.random() < 0.35 if failure.decline_code == "AUTHENTICATION_REQUIRED" else random.random() < 0.18
                result["recovered"] = reopen
                result["outbox_file"] = str(path)
                result["mode"] = "dunning_stub"
                s.add(
                    OutcomeRow(
                        failure_id=failure.id,
                        recovered=reopen,
                        recovered_amount=float(failure.amount_inr) if reopen else 0.0,
                        source="dunning",
                        details_json=json.dumps(result),
                    )
                )
                failure.status = FailureStatus.RECOVERED.value if reopen else FailureStatus.EXECUTED.value
            elif action == RecoveryAction.ESCALATE_MANUAL.value:
                result["recovered"] = False
                result["mode"] = "escalated"
                failure.status = FailureStatus.OPEN.value
                s.add(
                    OutcomeRow(
                        failure_id=failure.id,
                        recovered=False,
                        recovered_amount=0.0,
                        source="manual",
                        details_json=json.dumps(result),
                    )
                )
            else:
                result["recovered"] = False
                result["mode"] = "no_op"
                failure.status = FailureStatus.ABANDONED.value
                s.add(
                    OutcomeRow(
                        failure_id=failure.id,
                        recovered=False,
                        recovered_amount=0.0,
                        source="manual",
                        details_json=json.dumps(result),
                    )
                )

            job.status = JobStatus.DONE.value
            job.updated_at = utcnow()
            failure.updated_at = utcnow()
            s.add(JobExecutionRow(job_id=job_id, result_json=json.dumps(result), error=None))
            s.commit()
            write_audit("worker", "job_executed", "recovery_job", job_id, result)
            logger.info("Executed %s action=%s recovered=%s", job_id, action, result.get("recovered"))
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED.value
            job.updated_at = utcnow()
            s.add(JobExecutionRow(job_id=job_id, result_json="{}", error=str(exc)))
            s.commit()
            logger.exception("Job %s failed", job_id)
            return {"ok": False, "error": str(exc)}


def process_once(limit: int = 20) -> int:
    ids = claim_due_jobs(limit=limit)
    for jid in ids:
        execute_job(jid)
    return len(ids)


def run_forever(poll_seconds: float = WORKER_POLL_SECONDS) -> None:
    get_engine()
    seed_demo_merchant()
    logger.info("Recovery worker started (poll=%.1fs)", poll_seconds)
    while True:
        n = process_once()
        if n == 0:
            time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="RecoverPilot recovery worker")
    parser.add_argument("--once", action="store_true", help="Process due jobs once and exit")
    parser.add_argument("--poll", type=float, default=WORKER_POLL_SECONDS)
    args = parser.parse_args()
    get_engine()
    seed_demo_merchant()
    if args.once:
        n = process_once()
        print(f"processed={n}")
    else:
        run_forever(poll_seconds=args.poll)


if __name__ == "__main__":
    main()
