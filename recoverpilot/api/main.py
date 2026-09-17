from __future__ import annotations

import json
import secrets
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from recoverpilot.agent.rag import get_rag
from recoverpilot.core import db
from recoverpilot.core.auth import require_merchant
from recoverpilot.core.config import (
    DEMO_API_KEY,
    DEMO_MERCHANT_ID,
    DEMO_TIME_SCALE,
    DEMO_WEBHOOK_SECRET,
    PROJECT_ROOT,
    RAZORPAY_WEBHOOK_SECRET,
)
from recoverpilot.core.db import MerchantRow, OutcomeRow, RecoveryJobRow, session, utcnow, write_audit
from recoverpilot.core.schemas import (
    HealthResponse,
    KPIResponse,
    OutcomeCreateRequest,
    OverrideRequest,
    PaymentFailureEvent,
    RecommendResponse,
    ScoreRequest,
    ScoreResponse,
    SimulateRequest,
    SimulateResponse,
    WebhookIngestResponse,
)
from recoverpilot.integrations.razorpay_webhooks import (
    build_sample_payment_failed,
    normalize_razorpay_payload,
    verify_signature,
)
from recoverpilot.ml.scorer import model_loaded
from recoverpilot.services import orchestrator, pipeline
from recoverpilot.services.demo_story import demo_story, write_eval_summary
from recoverpilot.services.magic_link import confirm_magic_link, create_magic_link, inspect_magic_link
from recoverpilot.ui.portal_html import portal_page
from recoverpilot.workers.recovery_worker import execute_job, process_once

app = FastAPI(
    title="RecoverPilot API",
    description="Production-like failed-payment recovery engine (AI Revenue Recovery)",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.get_engine()
    db.seed_demo_merchant()
    try:
        write_eval_summary()
    except Exception:
        pass
    try:
        from recoverpilot.ml.scorer import load_model_bundle

        load_model_bundle()
    except Exception:
        pass
    try:
        get_rag()
    except Exception:
        pass


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    playbooks_ok = True
    try:
        rag = get_rag()
        mode = rag.mode
    except Exception as exc:
        playbooks_ok = False
        mode = str(exc)
    return HealthResponse(
        status="ok",
        model_loaded=model_loaded(),
        playbooks_loaded=playbooks_ok,
        details={
            "rag_mode": mode,
            "demo_time_scale": DEMO_TIME_SCALE,
            "demo_api_key_hint": DEMO_API_KEY[:8] + "...",
            "merchant_id": DEMO_MERCHANT_ID,
        },
    )


@app.get("/demo/story")
def get_demo_story() -> dict[str, Any]:
    """Recruiter-facing 60-second story + canonical proof numbers (no auth)."""
    return demo_story()


# ---- legacy / interview demo endpoints ----

@app.post("/events/ingest")
def ingest(event: PaymentFailureEvent, merchant: MerchantRow = Depends(require_merchant)) -> dict:
    return orchestrator.ingest_event(event)


@app.post("/recover/score", response_model=ScoreResponse)
def recover_score(req: ScoreRequest) -> ScoreResponse:
    return orchestrator.score(req.event)


@app.post("/recover/recommend", response_model=RecommendResponse)
def recover_recommend(event: PaymentFailureEvent) -> RecommendResponse:
    return orchestrator.recommend(event, enqueue_job=True)


@app.post("/recover/simulate", response_model=SimulateResponse)
def recover_simulate(req: SimulateRequest) -> SimulateResponse:
    return orchestrator.simulate(req.sample_size)


@app.post("/admin/override")
def admin_override(req: OverrideRequest, merchant: MerchantRow = Depends(require_merchant)) -> dict:
    return orchestrator.apply_override(req)


@app.get("/events/recent")
def recent_events(limit: int = 50) -> list[dict]:
    return db.list_recent_events(limit=limit)


@app.get("/events/{event_id}")
def get_event(event_id: str) -> dict:
    row = db.get_event(event_id)
    if not row:
        fail = db.get_failure(event_id)
        if fail:
            return db.failure_to_dict(fail)
        raise HTTPException(status_code=404, detail="Event not found")
    return row


# ---- production-like endpoints ----

@app.post("/webhooks/razorpay", response_model=WebhookIngestResponse)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(default=None, alias="X-Razorpay-Signature"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> WebhookIngestResponse:
    body = await request.body()
    merchant = None
    if x_api_key:
        merchant = db.get_merchant_by_api_key(x_api_key)
    if merchant is None:
        merchant = db.get_merchant(DEMO_MERCHANT_ID)
    if merchant is None:
        raise HTTPException(status_code=500, detail="Demo merchant not seeded")

    secret = RAZORPAY_WEBHOOK_SECRET or merchant.webhook_secret or DEMO_WEBHOOK_SECRET
    if RAZORPAY_WEBHOOK_SECRET:
        if not verify_signature(body, x_razorpay_signature, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    elif x_razorpay_signature:
        if not verify_signature(body, x_razorpay_signature, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    event_name = payload.get("event") or payload.get("event_name") or "payment.failed"
    if event_name not in {"payment.failed", "payment.authorized"} and "payment" not in str(event_name):
        pass

    event = normalize_razorpay_payload(payload, merchant_id=merchant.id, merchant_category=merchant.category)
    return pipeline.ingest_webhook_event(event, raw_payload=payload)


@app.post("/admin/seed")
def admin_seed(
    count: int = Query(default=5, ge=1, le=50),
    merchant: MerchantRow = Depends(require_merchant),
) -> dict[str, Any]:
    declines = [
        "INSUFFICIENT_FUNDS",
        "ISSUER_TIMEOUT",
        "AUTHENTICATION_REQUIRED",
        "NETWORK_ERROR",
        "STOLEN_CARD",
        "BANK_DECLINE_SOFT",
    ]
    created = []
    for i in range(count):
        pay_id = f"pay_seed_{secrets.token_hex(4)}"
        decline = declines[i % len(declines)]
        amount = 299 + i * 50
        payload = build_sample_payment_failed(
            payment_id=pay_id,
            amount_inr=float(amount),
            decline_code=decline,
            method="upi" if i % 2 == 0 else "card",
        )
        event = normalize_razorpay_payload(payload, merchant_id=merchant.id, merchant_category=merchant.category)
        resp = pipeline.ingest_webhook_event(event, raw_payload=payload)
        created.append(resp.model_dump())
    write_audit(merchant.id, "seed", "system", "seed", {"count": count})
    return {"seeded": len(created), "items": created}


@app.get("/failures")
def list_failures(
    limit: int = 100,
    status: Optional[str] = None,
    merchant: MerchantRow = Depends(require_merchant),
) -> list[dict]:
    return db.list_failures(limit=limit, status=status, merchant_id=merchant.id)


@app.get("/failures/{failure_id}")
def get_failure(failure_id: str, merchant: MerchantRow = Depends(require_merchant)) -> dict:
    row = db.get_failure(failure_id)
    if not row or row.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Failure not found")
    return db.failure_to_dict(row)


@app.get("/jobs")
def list_jobs(
    limit: int = 100,
    status: Optional[str] = None,
    merchant: MerchantRow = Depends(require_merchant),
) -> list[dict]:
    _ = merchant
    return db.list_jobs(limit=limit, status=status)


@app.post("/jobs/{job_id}/run")
def run_job(job_id: str, merchant: MerchantRow = Depends(require_merchant)) -> dict:
    _ = merchant
    with session() as s:
        job = s.get(RecoveryJobRow, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        job.run_at = utcnow()
        if job.status == "pending":
            pass
        elif job.status in {"done", "failed"}:
            job.status = "pending"
            job.run_at = utcnow()
        s.commit()
    return execute_job(job_id)


@app.post("/jobs/process-due")
def process_due(merchant: MerchantRow = Depends(require_merchant)) -> dict:
    _ = merchant
    n = process_once(limit=50)
    return {"processed": n}


@app.post("/outcomes/{failure_id}")
def create_outcome(
    failure_id: str,
    req: OutcomeCreateRequest,
    merchant: MerchantRow = Depends(require_merchant),
) -> dict:
    row = db.get_failure(failure_id)
    if not row or row.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Failure not found")
    from recoverpilot.core.db import PaymentFailureRow

    with session() as s:
        s.add(
            OutcomeRow(
                failure_id=failure_id,
                recovered=req.recovered,
                recovered_amount=req.recovered_amount,
                source=req.source,
                details_json=json.dumps(req.details),
            )
        )
        fail = s.get(PaymentFailureRow, failure_id)
        if fail:
            fail.status = "recovered" if req.recovered else "executed"
            fail.updated_at = utcnow()
        s.commit()
    return {"status": "ok", "failure_id": failure_id}


@app.get("/outcomes")
def outcomes(limit: int = 100, merchant: MerchantRow = Depends(require_merchant)) -> list[dict]:
    _ = merchant
    return db.list_outcomes(limit=limit)


@app.get("/kpis", response_model=KPIResponse)
def kpis(merchant: MerchantRow = Depends(require_merchant)) -> KPIResponse:
    _ = merchant
    return KPIResponse(**pipeline.get_kpis())


@app.post("/admin/retrain")
def admin_retrain(merchant: MerchantRow = Depends(require_merchant)) -> dict:
    _ = merchant
    from recoverpilot.ml.retrain import retrain

    metrics = retrain(merge_synthetic=True)
    write_audit(merchant.id, "retrain", "model", metrics.get("version", "unknown"), metrics)
    return metrics


@app.get("/admin/demo-credentials")
def demo_credentials() -> dict:
    """Public hint for local demo only."""
    return {
        "merchant_id": DEMO_MERCHANT_ID,
        "api_key": DEMO_API_KEY,
        "webhook_secret": DEMO_WEBHOOK_SECRET,
        "note": "Local demo credentials. Change via env vars before any shared deploy.",
    }


@app.post("/admin/magic-link/{failure_id}")
def admin_create_magic_link(failure_id: str, merchant: MerchantRow = Depends(require_merchant)) -> dict:
    row = db.get_failure(failure_id)
    if not row or row.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Failure not found")
    return create_magic_link(failure_id, float(row.amount_inr), row.decline_code)


@app.get("/recover/{token}", response_class=HTMLResponse)
def recover_portal(token: str) -> HTMLResponse:
    info = inspect_magic_link(token)
    html = portal_page(
        status=info.get("status", "invalid"),
        amount_inr=info.get("amount_inr"),
        decline_code=info.get("decline_code"),
        expires_at=info.get("expires_at"),
        token=token if info.get("status") == "active" else None,
    )
    return HTMLResponse(content=html)


@app.post("/recover/{token}/confirm", response_class=HTMLResponse)
def recover_confirm(token: str) -> HTMLResponse:
    result = confirm_magic_link(token)
    if result.get("ok"):
        html = portal_page(
            status="recovered",
            amount_inr=result.get("recovered_amount"),
            message=result.get("message"),
        )
    else:
        html = portal_page(status=result.get("error", "invalid"), message=result.get("message"))
    return HTMLResponse(content=html)


@app.get("/recover/{token}/status")
def recover_status(token: str) -> dict:
    return inspect_magic_link(token)


@app.post("/recover/{token}/confirm.json")
def recover_confirm_json(token: str) -> dict:
    return confirm_magic_link(token)


# Recruiter console (public/index.html) at /console/
_public = PROJECT_ROOT / "public"
if _public.is_dir():
    app.mount("/console", StaticFiles(directory=str(_public), html=True), name="console")
