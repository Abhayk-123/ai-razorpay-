"""Generate synthetic failed-payment events with recoverable outcome labels.

ASSUMPTION: This is synthetic data for demo/training. It is NOT Razorpay production data.
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from recoverpilot.core.config import (
    HARD_DECLINE_CODES,
    RANDOM_SEED,
    SOFT_DECLINE_CODES,
    SYNTHETIC_CSV,
)
from recoverpilot.core.paths import ensure_dirs

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]
ISSUER_BUCKETS = ["hdfc", "icici", "sbi", "axis", "kotak", "other"]
MERCHANT_CATEGORIES = ["saas", "edtech", "ecommerce", "media", "utilities"]


def _recovery_probability(row: dict, rng: np.random.Generator) -> float:
    """Latent success probability used only to generate labels."""
    code = row["decline_code"]
    if code in HARD_DECLINE_CODES:
        return 0.02

    base = {
        "INSUFFICIENT_FUNDS": 0.42,
        "ISSUER_TIMEOUT": 0.68,
        "NETWORK_ERROR": 0.70,
        "BANK_DECLINE_SOFT": 0.38,
        "AUTHENTICATION_REQUIRED": 0.55,
        "EXCEEDS_FREQUENCY": 0.33,
        "TEMPORARY_HOLD": 0.40,
    }.get(code, 0.35)

    # Timing effects
    if code == "INSUFFICIENT_FUNDS" and row["hour_of_day"] in {9, 10, 11, 18, 19, 20}:
        base += 0.08
    if code in {"ISSUER_TIMEOUT", "NETWORK_ERROR"} and row["attempt_number"] == 1:
        base += 0.10

    # Customer / amount effects
    if row["customer_tenure_days"] > 180:
        base += 0.06
    if row["amount_inr"] > 5000:
        base -= 0.07
    if row["attempt_number"] >= 4:
        base -= 0.12
    if row["payment_method"] == "upi":
        base += 0.03

    noise = rng.normal(0, 0.05)
    return float(np.clip(base + noise, 0.01, 0.95))


def generate_dataset(n_rows: int = 20000, seed: int = RANDOM_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    soft = list(SOFT_DECLINE_CODES)
    hard = list(HARD_DECLINE_CODES)

    rows = []
    for _ in range(n_rows):
        is_hard = rng.random() < 0.18
        decline_code = rng.choice(hard if is_hard else soft)
        row = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "merchant_id": f"mch_{rng.integers(1, 400):04d}",
            "customer_id": f"cus_{rng.integers(1, 8000):05d}",
            "amount_inr": float(np.round(rng.lognormal(mean=6.2, sigma=0.7), 2)),
            "payment_method": rng.choice(PAYMENT_METHODS, p=[0.45, 0.35, 0.12, 0.08]),
            "issuer_bucket": rng.choice(ISSUER_BUCKETS),
            "decline_code": decline_code,
            "attempt_number": int(rng.choice([1, 2, 3, 4, 5], p=[0.45, 0.25, 0.15, 0.10, 0.05])),
            "hour_of_day": int(rng.integers(0, 24)),
            "day_of_week": int(rng.integers(0, 7)),
            "merchant_category": rng.choice(MERCHANT_CATEGORIES),
            "customer_tenure_days": int(rng.integers(0, 1000)),
            "is_subscription": bool(rng.random() < 0.75),
        }
        p = _recovery_probability(row, rng)
        row["p_latent"] = p
        row["recovered"] = int(rng.random() < p)
        rows.append(row)

    df = pd.DataFrame(rows)
    # Clamp extreme amounts for demo realism
    df["amount_inr"] = df["amount_inr"].clip(49, 50000)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic payment failure dataset")
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--out", type=Path, default=SYNTHETIC_CSV)
    args = parser.parse_args()

    ensure_dirs()
    df = generate_dataset(n_rows=args.rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df):,} rows -> {args.out}")
    print("Recovery rate:", round(df["recovered"].mean(), 4))
    print("Hard-decline share:", round(df["decline_code"].isin(HARD_DECLINE_CODES).mean(), 4))


if __name__ == "__main__":
    main()
