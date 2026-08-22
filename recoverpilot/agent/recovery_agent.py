"""Constrained recovery agent — policy + tools, not a free-form chatbot."""

from __future__ import annotations

from typing import Any

from recoverpilot.agent.rag import get_rag
from recoverpilot.core.config import HARD_DECLINE_CODES
from recoverpilot.core.schemas import RecoveryAction


def _tool_do_not_retry(playbook: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": RecoveryAction.DO_NOT_RETRY,
        "retry_after_hours": None,
        "channel": "none",
        "policy_notes": ["Hard decline policy: auto-retry blocked"],
        "playbook_id": playbook["id"],
    }


def _tool_schedule_retry(playbook: dict[str, Any], p_recovery: float) -> dict[str, Any]:
    hours = playbook.get("retry_after_hours") or 18
    # Adaptive tweak from model confidence
    if p_recovery >= 0.65:
        hours = max(1.0, float(hours) * 0.75)
    elif p_recovery < 0.25:
        hours = float(hours) * 1.25
    return {
        "action": RecoveryAction.SCHEDULE_RETRY,
        "retry_after_hours": round(float(hours), 2),
        "channel": playbook.get("channel") or "silent_retry",
        "policy_notes": ["Retry scheduled under soft-decline policy"],
        "playbook_id": playbook["id"],
    }


def _tool_send_dunning(playbook: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": RecoveryAction.SEND_DUNNING,
        "retry_after_hours": playbook.get("retry_after_hours") or 6,
        "channel": playbook.get("channel") or "email_sms",
        "policy_notes": ["Customer action required — dunning preferred over silent retry"],
        "playbook_id": playbook["id"],
    }


def _tool_escalate(playbook: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": RecoveryAction.ESCALATE_MANUAL,
        "retry_after_hours": None,
        "channel": "ops_queue",
        "policy_notes": ["High-value / ambiguous case escalated to human ops"],
        "playbook_id": playbook["id"],
    }


def decide_recovery_action(
    event: dict[str, Any],
    p_recovery: float,
    expected_value_inr: float,
    is_hard_decline: bool,
) -> dict[str, Any]:
    rag = get_rag().retrieve(event["decline_code"], query_extra=event.get("merchant_category", ""))
    playbook = rag["playbook"]

    if is_hard_decline or event["decline_code"] in HARD_DECLINE_CODES or not playbook.get("recoverable", True):
        decision = _tool_do_not_retry(playbook)
    elif playbook.get("preferred_action") == "send_dunning" or event["decline_code"] == "AUTHENTICATION_REQUIRED":
        decision = _tool_send_dunning(playbook)
    elif expected_value_inr >= 3000 and p_recovery < 0.35:
        decision = _tool_escalate(playbook)
    elif p_recovery < 0.12:
        decision = _tool_do_not_retry(playbook)
        decision["policy_notes"] = ["Low recovery probability — suppress wasted retries"]
    else:
        preferred = playbook.get("preferred_action", "schedule_retry")
        if preferred == "escalate_manual":
            decision = _tool_escalate(playbook)
        elif preferred == "send_dunning":
            decision = _tool_send_dunning(playbook)
        else:
            decision = _tool_schedule_retry(playbook, p_recovery)

    decision["playbook_excerpt"] = rag["excerpt"]
    decision["retrieval_mode"] = rag["retrieval_mode"]
    return decision


def build_explanation(
    event: dict[str, Any],
    p_recovery: float,
    expected_value_inr: float,
    decision: dict[str, Any],
    contributions: dict[str, float],
) -> str:
    top = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
    top_txt = ", ".join(f"{k} ({v:+.3f})" for k, v in top)
    return (
        f"Decline `{event['decline_code']}` scored P(recovery)={p_recovery:.2%} "
        f"and expected value ₹{expected_value_inr:.2f}. "
        f"Recommended action: `{decision['action'].value if hasattr(decision['action'], 'value') else decision['action']}`. "
        f"Grounded playbook: {decision['playbook_id']}. "
        f"Key local drivers: {top_txt}. "
        f"Policy: {'; '.join(decision.get('policy_notes', []))}."
    )
