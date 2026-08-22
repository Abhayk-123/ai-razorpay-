from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from recoverpilot.agent.recovery_agent import build_explanation, decide_recovery_action
from recoverpilot.core import db
from recoverpilot.core.config import HARD_DECLINE_CODES, RETRY_COST_INR, SYNTHETIC_CSV
from recoverpilot.core.schemas import (
    OverrideRequest,
    PaymentFailureEvent,
    RecommendResponse,
    RecoveryAction,
    ScoreResponse,
    SimulateResponse,
)
from recoverpilot.ml.scorer import approximate_contributions, score_event
from recoverpilot.services import pipeline


def ingest_event(event: PaymentFailureEvent) -> dict[str, Any]:
    payload = event.model_dump(mode="json")
    db.upsert_event(event.event_id, payload)
    return payload


def score(event: PaymentFailureEvent) -> ScoreResponse:
    payload = ingest_event(event)
    result = score_event(payload)
    db.save_score(
        event_id=event.event_id,
        p_recovery=result["p_recovery"],
        expected_value_inr=result["expected_value_inr"],
        is_hard_decline=result["is_hard_decline"],
        model_version=result["model_version"],
    )
    return ScoreResponse(event_id=event.event_id, **result)


def recommend(event: PaymentFailureEvent, enqueue_job: bool = True) -> RecommendResponse:
    """Recommend recovery action. When enqueue_job=True, persists failure + recovery job."""
    if enqueue_job:
        return pipeline.persist_and_recommend(event)
    payload = ingest_event(event)
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
    resp = RecommendResponse(
        event_id=event.event_id,
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
    )
    db.save_score(
        event_id=event.event_id,
        p_recovery=scored["p_recovery"],
        expected_value_inr=scored["expected_value_inr"],
        is_hard_decline=scored["is_hard_decline"],
        model_version=scored["model_version"],
    )
    db.save_action(event.event_id, resp.action.value, resp.model_dump(mode="json"))
    return resp


def apply_override(req: OverrideRequest) -> dict[str, Any]:
    db.save_override(req.event_id, req.action.value, req.reason, req.operator)
    # Re-enqueue job under override policy
    job_id = pipeline.create_job_for_recommendation(
        failure_id=req.event_id,
        action=req.action,
        retry_after_hours=1.0 if req.action == RecoveryAction.SCHEDULE_RETRY else 0.5,
        channel="override",
        extra={"override_reason": req.reason, "operator": req.operator},
    )
    db.write_audit(req.operator, "override", "payment_failure", req.event_id, {"action": req.action.value})
    return {"status": "ok", "event_id": req.event_id, "action": req.action.value, "job_id": job_id}


def _blind_retry_policy(row: pd.Series) -> tuple[bool, float]:
    if row["decline_code"] in HARD_DECLINE_CODES:
        return False, 0.0
    return True, 24.0


def simulate(sample_size: int = 500) -> SimulateResponse:
    if SYNTHETIC_CSV.exists():
        df = pd.read_csv(SYNTHETIC_CSV)
    else:
        from recoverpilot.data.generate import generate_dataset

        df = generate_dataset(n_rows=max(sample_size, 2000))

    sample = df.sample(n=min(sample_size, len(df)), random_state=42)

    baseline_recovered = 0.0
    rp_recovered = 0.0
    baseline_retries = 0
    rp_retries = 0

    for _, row in sample.iterrows():
        event = row.to_dict()
        recovered_flag = int(row["recovered"])
        amount = float(row["amount_inr"])

        will_retry, _ = _blind_retry_policy(row)
        if will_retry:
            baseline_retries += 1
            success = recovered_flag and (np.random.random() < 0.85)
            if success:
                baseline_recovered += amount - RETRY_COST_INR
            else:
                baseline_recovered -= RETRY_COST_INR

        scored = score_event(event)
        decision = decide_recovery_action(
            event,
            scored["p_recovery"],
            scored["expected_value_inr"],
            scored["is_hard_decline"],
        )
        action = decision["action"]
        action_val = action.value if isinstance(action, RecoveryAction) else str(action)

        if (
            action_val in {RecoveryAction.SCHEDULE_RETRY.value, RecoveryAction.SEND_DUNNING.value}
            and scored["expected_value_inr"] >= RETRY_COST_INR * 2
            and scored["p_recovery"] >= 0.22
        ):
            rp_retries += 1
            success = recovered_flag and scored["p_recovery"] >= 0.22
            if action_val == RecoveryAction.SEND_DUNNING and row["decline_code"] == "AUTHENTICATION_REQUIRED":
                success = bool(recovered_flag)
            if success:
                rp_recovered += amount - RETRY_COST_INR
            else:
                rp_recovered -= RETRY_COST_INR

    rel_lift = 0.0
    if abs(baseline_recovered) > 1e-6:
        rel_lift = (rp_recovered - baseline_recovered) / abs(baseline_recovered) * 100.0

    wasted_reduction = 0.0
    if baseline_retries > 0:
        wasted_reduction = (baseline_retries - rp_retries) / baseline_retries * 100.0

    return SimulateResponse(
        sample_size=int(len(sample)),
        baseline_recovered_inr=round(float(baseline_recovered), 2),
        recoverpilot_recovered_inr=round(float(rp_recovered), 2),
        baseline_retries=int(baseline_retries),
        recoverpilot_retries=int(rp_retries),
        relative_lift_pct=round(float(rel_lift), 2),
        wasted_retry_reduction_pct=round(float(wasted_reduction), 2),
        notes=(
            "Offline simulation on synthetic labeled failures. "
            "Relative lift is a demo KPI, not production causal A/B lift."
        ),
    )


def rank_queue(events: list[PaymentFailureEvent], top_k: int = 50) -> list[dict[str, Any]]:
    ranked = []
    for ev in events:
        scored = score_event(ev.model_dump())
        ranked.append(
            {
                "event": ev,
                "p_recovery": scored["p_recovery"],
                "expected_value_inr": scored["expected_value_inr"],
            }
        )
    ranked.sort(key=lambda x: x["expected_value_inr"], reverse=True)
    return ranked[:top_k]
