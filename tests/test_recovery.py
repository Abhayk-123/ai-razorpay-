from recoverpilot.core.schemas import PaymentFailureEvent
from recoverpilot.services.orchestrator import recommend


def test_hard_decline_never_retries():
    event = PaymentFailureEvent(
        event_id="evt_test_hard",
        merchant_id="mch_0001",
        customer_id="cus_00001",
        amount_inr=999.0,
        payment_method="card",
        issuer_bucket="hdfc",
        decline_code="STOLEN_CARD",
        attempt_number=1,
        hour_of_day=10,
        day_of_week=1,
        merchant_category="saas",
        customer_tenure_days=100,
        is_subscription=True,
    )
    rec = recommend(event)
    assert rec.action.value == "do_not_retry"
    assert rec.expected_value_inr == 0


def test_soft_decline_gets_action():
    event = PaymentFailureEvent(
        event_id="evt_test_soft",
        merchant_id="mch_0002",
        customer_id="cus_00002",
        amount_inr=499.0,
        payment_method="upi",
        issuer_bucket="sbi",
        decline_code="INSUFFICIENT_FUNDS",
        attempt_number=1,
        hour_of_day=19,
        day_of_week=2,
        merchant_category="saas",
        customer_tenure_days=400,
        is_subscription=True,
    )
    rec = recommend(event)
    assert rec.action.value in {"schedule_retry", "send_dunning", "escalate_manual", "do_not_retry"}
    assert rec.playbook_id
    assert rec.explanation
