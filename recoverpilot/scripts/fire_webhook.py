"""Fire Razorpay-shaped payment.failed webhooks at the local API."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets

import httpx

from recoverpilot.core.config import API_BASE_URL, DEMO_API_KEY, DEMO_WEBHOOK_SECRET, RAZORPAY_WEBHOOK_SECRET
from recoverpilot.integrations.razorpay_webhooks import build_sample_payment_failed


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--base", default=API_BASE_URL)
    parser.add_argument("--api-key", default=DEMO_API_KEY)
    parser.add_argument("--secret", default=RAZORPAY_WEBHOOK_SECRET or DEMO_WEBHOOK_SECRET)
    parser.add_argument(
        "--decline",
        default=None,
        help="Force a decline code, e.g. INSUFFICIENT_FUNDS or STOLEN_CARD",
    )
    args = parser.parse_args()

    declines = [
        "INSUFFICIENT_FUNDS",
        "ISSUER_TIMEOUT",
        "AUTHENTICATION_REQUIRED",
        "NETWORK_ERROR",
        "STOLEN_CARD",
        "BANK_DECLINE_SOFT",
    ]
    with httpx.Client(timeout=60) as client:
        for i in range(args.count):
            decline = args.decline or declines[i % len(declines)]
            pay_id = f"pay_fire_{secrets.token_hex(4)}"
            payload = build_sample_payment_failed(
                payment_id=pay_id,
                amount_inr=float(499 + i * 100),
                decline_code=decline,
            )
            body = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": args.api_key,
                "X-Razorpay-Signature": sign(body, args.secret),
            }
            r = client.post(f"{args.base}/webhooks/razorpay", content=body, headers=headers)
            print(r.status_code, r.text)


if __name__ == "__main__":
    main()
