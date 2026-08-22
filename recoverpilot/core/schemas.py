from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class RecoveryAction(str, Enum):
    SCHEDULE_RETRY = "schedule_retry"
    SEND_DUNNING = "send_dunning"
    ESCALATE_MANUAL = "escalate_manual"
    DO_NOT_RETRY = "do_not_retry"


class FailureStatus(str, Enum):
    OPEN = "open"
    SCHEDULED = "scheduled"
    EXECUTED = "executed"
    RECOVERED = "recovered"
    ABANDONED = "abandoned"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentFailureEvent(BaseModel):
    event_id: str
    merchant_id: str
    customer_id: str
    amount_inr: float = Field(gt=0)
    payment_method: str
    issuer_bucket: str
    decline_code: str
    attempt_number: int = Field(ge=1)
    hour_of_day: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)
    merchant_category: str
    customer_tenure_days: int = Field(ge=0)
    is_subscription: bool = True
    created_at: Optional[datetime] = None
    external_payment_id: Optional[str] = None
    webhook_event_id: Optional[str] = None


class ScoreRequest(BaseModel):
    event: PaymentFailureEvent


class ScoreResponse(BaseModel):
    event_id: str
    p_recovery: float
    expected_value_inr: float
    is_hard_decline: bool
    model_version: str


class RecommendResponse(BaseModel):
    event_id: str
    p_recovery: float
    expected_value_inr: float
    action: RecoveryAction
    retry_after_hours: Optional[float] = None
    channel: Optional[str] = None
    playbook_id: str
    playbook_excerpt: str
    explanation: str
    feature_contributions: dict[str, float] = Field(default_factory=dict)
    policy_notes: list[str] = Field(default_factory=list)
    job_id: Optional[str] = None


class OverrideRequest(BaseModel):
    event_id: str
    action: RecoveryAction
    reason: str
    operator: str = "demo_user"


class SimulateRequest(BaseModel):
    sample_size: int = Field(default=500, ge=50, le=5000)


class SimulateResponse(BaseModel):
    sample_size: int
    baseline_recovered_inr: float
    recoverpilot_recovered_inr: float
    baseline_retries: int
    recoverpilot_retries: int
    relative_lift_pct: float
    wasted_retry_reduction_pct: float
    notes: str


class QueueItem(BaseModel):
    event: PaymentFailureEvent
    p_recovery: float
    expected_value_inr: float
    recommended_action: Optional[RecoveryAction] = None


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    playbooks_loaded: bool
    details: dict[str, Any] = Field(default_factory=dict)


class WebhookIngestResponse(BaseModel):
    status: str
    failure_id: str
    duplicate: bool = False
    recommendation: Optional[RecommendResponse] = None
    job_id: Optional[str] = None


class OutcomeCreateRequest(BaseModel):
    recovered: bool
    recovered_amount: float = 0.0
    source: str = "manual"
    details: dict[str, Any] = Field(default_factory=dict)


class KPIResponse(BaseModel):
    failures_total: int
    recovered_count: int
    abandoned_count: int
    pending_jobs: int
    recovered_amount_inr: float
    recovery_rate: float
