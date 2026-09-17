"""Optional Razorpay Payment Link creation (Test Mode only)."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from recoverpilot.core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, USE_RAZORPAY_PAYMENT_LINKS

logger = logging.getLogger(__name__)


def payment_links_enabled() -> bool:
    return bool(
        USE_RAZORPAY_PAYMENT_LINKS
        and RAZORPAY_KEY_ID.startswith("rzp_test_")
        and RAZORPAY_KEY_SECRET
    )


def create_payment_link(
    *,
    amount_inr: float,
    failure_id: str,
    customer_id: str,
    description: str | None = None,
) -> Optional[dict[str, Any]]:
    """Create a Razorpay Test Mode payment link. Returns None if disabled or on error."""
    if not payment_links_enabled():
        return None
    if RAZORPAY_KEY_ID.startswith("rzp_live_"):
        logger.warning("Refusing live Razorpay keys for payment-link executor")
        return None

    amount_paise = int(round(float(amount_inr) * 100))
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "accept_partial": False,
        "description": description or f"RecoverPilot recovery for {failure_id}",
        "reference_id": failure_id[:40],
        "notes": {"failure_id": failure_id, "customer_id": customer_id, "source": "recoverpilot"},
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.razorpay.com/v1/payment_links",
                json=payload,
                auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            )
        if resp.status_code >= 400:
            logger.error("Payment link create failed: %s %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        return {
            "id": data.get("id"),
            "short_url": data.get("short_url"),
            "status": data.get("status"),
            "mode": "razorpay_test_payment_link",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Payment link create error: %s", exc)
        return None
