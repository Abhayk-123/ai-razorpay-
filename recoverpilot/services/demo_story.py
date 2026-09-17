"""Reproducible recruiter-facing demo story + eval summary helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from recoverpilot.core.config import ARTIFACTS_DIR, HARD_DECLINE_CODES

# Stable headline numbers for public demo (also written to artifacts/eval_summary.json).
# Sourced from offline simulate(sample_size=500, seed-stable path); kept fixed so
# the live UI never shows random recruiter-facing KPIs.
CANONICAL_EVAL: dict[str, Any] = {
    "sample_size": 500,
    "baseline_recovered_inr": 129588.04,
    "recoverpilot_recovered_inr": 157262.0,
    "baseline_retries": 415,
    "recoverpilot_retries": 415,
    "relative_lift_pct": 21.36,
    "wasted_retry_reduction_pct": 0.0,
    "hard_declines_in_sample": 85,
    "hard_declines_auto_retried": 0,
    "hard_decline_block_rate_pct": 100.0,
    "notes": (
        "Offline simulation on synthetic labeled failures (n=500). "
        "RecoverPilot recovered ~21% more INR vs blind soft-retry after cost. "
        "Hard declines are policy-blocked from auto-retry (100%). "
        "Relative lift is a demo KPI, not production causal A/B lift."
    ),
}


def demo_story() -> dict[str, Any]:
    """60-second story payload for public UI and /demo/story."""
    ev = CANONICAL_EVAL
    return {
        "product": "RecoverPilot",
        "tagline": "Intelligent failed-payment recovery — soft declines recover, hard declines never auto-retry.",
        "pitch": (
            "When a Razorpay payment fails, RecoverPilot scores recoverability, "
            "applies a policy-constrained playbook, schedules a job, executes via a worker, "
            "records the outcome, and can retrain from feedback."
        ),
        "proof": {
            "relative_lift_pct": ev["relative_lift_pct"],
            "wasted_retry_reduction_pct": ev["wasted_retry_reduction_pct"],
            "baseline_recovered_inr": ev["baseline_recovered_inr"],
            "recoverpilot_recovered_inr": ev["recoverpilot_recovered_inr"],
            "baseline_retries": ev["baseline_retries"],
            "recoverpilot_retries": ev["recoverpilot_retries"],
            "hard_decline_block_rate_pct": ev["hard_decline_block_rate_pct"],
            "sample_size": ev["sample_size"],
        },
        "steps": [
            {"id": 1, "title": "Seed failures", "detail": "Fire Razorpay-shaped payment.failed webhooks (idempotent ingest)."},
            {"id": 2, "title": "Soft success", "detail": "INSUFFICIENT_FUNDS / ISSUER_TIMEOUT → score → schedule_retry or dunning."},
            {"id": 3, "title": "Hard block", "detail": "STOLEN_CARD / FRAUD → do_not_retry; no recovery job created."},
            {"id": 4, "title": "Customer portal", "detail": "Auth failures get a 15-min magic link so the customer can confirm payment update."},
            {"id": 5, "title": "KPIs + retrain", "detail": "Outcomes feed KPIs and bump the model version (v1 → v2 → v3)."},
        ],
        "hard_decline_codes": sorted(HARD_DECLINE_CODES),
        "honest_limits": [
            "Retries/dunning are simulated unless Razorpay Test Mode keys are configured.",
            "Training starts synthetic; the retrain loop from outcomes is real.",
            "Vercel hosts a lightweight heuristic demo; full sklearn + worker run locally.",
        ],
        "eval_notes": ev["notes"],
    }


def write_eval_summary(path: Path | None = None) -> Path:
    out = path or (ARTIFACTS_DIR / "eval_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {**CANONICAL_EVAL, "source": "canonical_demo_story"}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def load_eval_summary() -> dict[str, Any]:
    path = ARTIFACTS_DIR / "eval_summary.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return dict(CANONICAL_EVAL)
