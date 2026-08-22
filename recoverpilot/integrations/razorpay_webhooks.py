"""Razorpay-shaped webhook normalization and signature checks."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from recoverpilot.core.config import HARD_DECLINE_CODES, RAZORPAY_WEBHOOK_SECRET, SOFT_DECLINE_CODES
from recoverpilot.core.schemas import PaymentFailureEvent

logger = logging.getLogger(__name__)

# Map common Razorpay error codes / reasons to internal decline codes
RAZORPAY_ERROR_MAP = {
    "insufficient_funds": "INSUFFICIENT_FUNDS",
    "payment_timed_out": "ISSUER_TIMEOUT",
    "gateway_error": "NETWORK_ERROR",
    "bank_technical_error": "NETWORK_ERROR",
    "authentication_failed": "AUTHENTICATION_REQUIRED",
    "otp_expired": "AUTHENTICATION_REQUIRED",
    "transaction_limit_exceeded": "EXCEEDS_FREQUENCY",
    "do_not_honour": "DO_NOT_HONOR_HARD",
    "stolen_card": "STOLEN_CARD",
    "lost_card": "LOST_CARD",
    "pick_up_card": "PICKUP_CARD",
    "fraudulent": "FRAUD_SUSPECTED",
    "invalid_card_number": "INVALID_CARD",
    "card_expired": "INVALID_CARD",
    "account_closed": "CLOSED_ACCOUNT",
}


def verify_signature(body: bytes, signature: str | None, secret: str | None = None) -> bool:
    """HMAC-SHA256 verification. If no secret configured, allow in dev mode."""
    effective = (secret or RAZORPAY_WEBHOOK_SECRET or "").strip()
    if not effective:
        logger.warning("Webhook signature skipped (dev mode — no secret configured)")
        return True
    if not signature:
        return False
    digest = hmac.new(effective.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _map_decline(error_code: str | None, error_reason: str | None, error_description: str | None) -> str:
    candidates = [error_code or "", error_reason or "", error_description or ""]
    blob = " ".join(candidates).lower().replace(" ", "_")
    for key, mapped in RAZORPAY_ERROR_MAP.items():
        if key in blob:
            return mapped
    # Heuristic
    if "insufficient" in blob:
        return "INSUFFICIENT_FUNDS"
    if "otp" in blob or "auth" in blob:
        return "AUTHENTICATION_REQUIRED"
    if "timeout" in blob or "timed" in blob:
        return "ISSUER_TIMEOUT"
    if any(h.lower() in blob for h in HARD_DECLINE_CODES):
        return next(h for h in HARD_DECLINE_CODES if h.lower() in blob)
    return "BANK_DECLINE_SOFT"


def _method_bucket(method: str | None) -> str:
    m = (method or "card").lower()
    if m in {"upi", "card", "netbanking", "wallet"}:
        return m
    if "bank" in m:
        return "netbanking"
    return "card"


def _issuer_bucket(bank: str | None, wallet: str | None) -> str:
    raw = (bank or wallet or "other").lower()
    for known in ("hdfc", "icici", "sbi", "axis", "kotak"):
        if known in raw:
            return known
    return "other"


def normalize_razorpay_payload(payload: dict[str, Any], merchant_id: str, merchant_category: str = "saas") -> PaymentFailureEvent:
    """Convert Razorpay payment.failed-shaped JSON into internal event."""
    event_id = str(payload.get("event_id") or payload.get("id") or "")
    entity = (
        payload.get("payload", {}).get("payment", {}).get("entity")
        or payload.get("payment", {}).get("entity")
        or payload.get("payment")
        or {}
    )
    if not isinstance(entity, dict):
        entity = {}

    payment_id = str(entity.get("id") or payload.get("payment_id") or f"pay_synth_{event_id[-8:]}")
    amount_paise = entity.get("amount")
    if amount_paise is None:
        amount_inr = float(payload.get("amount_inr") or 499)
    else:
        amount_inr = float(amount_paise) / 100.0

    error_code = entity.get("error_code") or payload.get("error_code")
    error_reason = entity.get("error_reason") or payload.get("error_reason")
    error_description = entity.get("error_description") or payload.get("error_description")
    decline = payload.get("decline_code") or _map_decline(error_code, error_reason, error_description)

    if decline not in HARD_DECLINE_CODES and decline not in SOFT_DECLINE_CODES:
        decline = "BANK_DECLINE_SOFT"

    now = datetime.now(timezone.utc)
    notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}
    customer_id = str(
        entity.get("customer_id")
        or notes.get("customer_id")
        or payload.get("customer_id")
        or f"cus_{payment_id[-6:]}"
    )
    attempt_number = int(notes.get("attempt_number") or payload.get("attempt_number") or 1)
    tenure = int(notes.get("customer_tenure_days") or payload.get("customer_tenure_days") or 90)

    return PaymentFailureEvent(
        event_id=event_id or f"evt_{payment_id}",
        merchant_id=merchant_id,
        customer_id=customer_id,
        amount_inr=max(amount_inr, 1.0),
        payment_method=_method_bucket(entity.get("method") or payload.get("payment_method")),
        issuer_bucket=_issuer_bucket(entity.get("bank"), entity.get("wallet")),
        decline_code=decline,
        attempt_number=max(attempt_number, 1),
        hour_of_day=now.hour,
        day_of_week=now.weekday() % 7,
        merchant_category=merchant_category or "saas",
        customer_tenure_days=max(tenure, 0),
        is_subscription=bool(notes.get("is_subscription", payload.get("is_subscription", True))),
        created_at=now,
        external_payment_id=payment_id,
        webhook_event_id=event_id or None,
    )


def build_sample_payment_failed(
    *,
    payment_id: str,
    amount_inr: float,
    decline_code: str,
    method: str = "upi",
    event_id: str | None = None,
) -> dict[str, Any]:
    """Helper used by seed scripts and UI to fire Razorpay-shaped events."""
    # Reverse map a few codes to razorpay-ish reasons
    reverse = {
        "INSUFFICIENT_FUNDS": ("insufficient_funds", "insufficient_funds"),
        "ISSUER_TIMEOUT": ("payment_timed_out", "payment_timed_out"),
        "NETWORK_ERROR": ("gateway_error", "gateway_error"),
        "AUTHENTICATION_REQUIRED": ("authentication_failed", "authentication_failed"),
        "STOLEN_CARD": ("stolen_card", "stolen_card"),
        "FRAUD_SUSPECTED": ("fraudulent", "fraudulent"),
        "EXCEEDS_FREQUENCY": ("transaction_limit_exceeded", "transaction_limit_exceeded"),
        "BANK_DECLINE_SOFT": ("bank_technical_error", "bank_technical_error"),
        "TEMPORARY_HOLD": ("bank_technical_error", "temporary_hold"),
        "DO_NOT_HONOR_HARD": ("do_not_honour", "do_not_honour"),
        "LOST_CARD": ("lost_card", "lost_card"),
        "PICKUP_CARD": ("pick_up_card", "pick_up_card"),
        "INVALID_CARD": ("invalid_card_number", "invalid_card_number"),
        "CLOSED_ACCOUNT": ("account_closed", "account_closed"),
    }
    code, reason = reverse.get(decline_code, ("bank_technical_error", decline_code.lower()))
    eid = event_id or f"evt_{payment_id}"
    return {
        "id": eid,
        "event": "payment.failed",
        "event_id": eid,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": int(round(amount_inr * 100)),
                    "currency": "INR",
                    "status": "failed",
                    "method": method,
                    "bank": "HDFC",
                    "error_code": code,
                    "error_description": f"Simulated failure: {decline_code}",
                    "error_reason": reason,
                    "notes": {
                        "customer_id": f"cus_{payment_id[-6:]}",
                        "attempt_number": 1,
                        "customer_tenure_days": 180,
                        "is_subscription": True,
                    },
                }
            }
        },
    }
