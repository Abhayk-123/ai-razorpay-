from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "amount_inr",
    "attempt_number",
    "hour_of_day",
    "day_of_week",
    "customer_tenure_days",
    "is_subscription",
    "payment_method",
    "issuer_bucket",
    "decline_code",
    "merchant_category",
]

CATEGORICAL = [
    "payment_method",
    "issuer_bucket",
    "decline_code",
    "merchant_category",
]

NUMERIC = [
    "amount_inr",
    "attempt_number",
    "hour_of_day",
    "day_of_week",
    "customer_tenure_days",
    "is_subscription",
]


def event_to_frame(event: dict[str, Any] | pd.Series) -> pd.DataFrame:
    if isinstance(event, pd.Series):
        data = event.to_dict()
    else:
        data = dict(event)
    row = {c: data.get(c) for c in FEATURE_COLUMNS}
    row["is_subscription"] = int(bool(row.get("is_subscription", True)))
    return pd.DataFrame([row])


def prepare_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    x = df[FEATURE_COLUMNS].copy()
    x["is_subscription"] = x["is_subscription"].astype(int)
    y = df["recovered"].astype(int).to_numpy()
    return x, y
