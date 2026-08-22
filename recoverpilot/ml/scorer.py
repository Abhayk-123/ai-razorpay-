from __future__ import annotations

from functools import lru_cache
from typing import Any

import joblib
import numpy as np

from recoverpilot.core.config import HARD_DECLINE_CODES, MODEL_PATH, RETRY_COST_INR
from recoverpilot.ml.features import event_to_frame


@lru_cache(maxsize=1)
def load_model_bundle() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        from recoverpilot.ml.train import train

        train()
    return joblib.load(MODEL_PATH)


def reload_model() -> None:
    """Clear cached model so retrained artifacts are picked up."""
    load_model_bundle.cache_clear()


def model_loaded() -> bool:
    return MODEL_PATH.exists()

def score_event(event: dict[str, Any]) -> dict[str, Any]:
    bundle = load_model_bundle()
    pipe = bundle["pipeline"]
    frame = event_to_frame(event)
    p = float(pipe.predict_proba(frame)[0, 1])
    hard = event["decline_code"] in HARD_DECLINE_CODES
    if hard:
        p = min(p, 0.05)
    amount = float(event["amount_inr"])
    expected_value = max(0.0, p * amount - RETRY_COST_INR)
    if hard:
        expected_value = 0.0
    return {
        "p_recovery": round(p, 6),
        "expected_value_inr": round(expected_value, 2),
        "is_hard_decline": hard,
        "model_version": f"{bundle.get('model_name', 'model')}-{bundle.get('version', 'v1')}",
    }


def approximate_contributions(event: dict[str, Any]) -> dict[str, float]:
    """Lightweight explanation without requiring SHAP at runtime."""
    bundle = load_model_bundle()
    pipe = bundle["pipeline"]
    frame = event_to_frame(event)
    base_p = float(pipe.predict_proba(frame)[0, 1])
    contribs: dict[str, float] = {}

    # Ablation-style local importance on key fields
    probes = {
        "amount_inr": max(99.0, float(event["amount_inr"]) * 0.5),
        "attempt_number": 1,
        "customer_tenure_days": max(365, int(event["customer_tenure_days"])),
        "hour_of_day": 10,
    }
    for key, alt in probes.items():
        tmp = dict(event)
        tmp[key] = alt
        alt_p = float(pipe.predict_proba(event_to_frame(tmp))[0, 1])
        contribs[key] = round(base_p - alt_p, 4)

    contribs["decline_code"] = round(0.15 if event["decline_code"] in HARD_DECLINE_CODES else 0.05, 4)
    return contribs
