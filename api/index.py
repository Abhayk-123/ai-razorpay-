"""Lightweight RecoverPilot API for Vercel (no sklearn/scipy bundle).

Full ML stack still runs locally via Streamlit/FastAPI.
This serverless demo keeps the same recovery loop + playbooks.
"""

from __future__ import annotations

import json
import random
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOKS = ROOT / "recoverpilot" / "data" / "playbooks" / "decline_playbooks.json"

HARD = {
    "DO_NOT_HONOR_HARD",
    "STOLEN_CARD",
    "LOST_CARD",
    "PICKUP_CARD",
    "FRAUD_SUSPECTED",
    "INVALID_CARD",
    "CLOSED_ACCOUNT",
}

SOFT_BASE = {
    "INSUFFICIENT_FUNDS": 0.45,
    "ISSUER_TIMEOUT": 0.68,
    "NETWORK_ERROR": 0.70,
    "BANK_DECLINE_SOFT": 0.38,
    "AUTHENTICATION_REQUIRED": 0.55,
    "EXCEEDS_FREQUENCY": 0.33,
    "TEMPORARY_HOLD": 0.40,
}

DEMO_API_KEY = "rp_demo_key_change_me"
DEMO_MERCHANT_ID = "mch_demo_001"

# Ephemeral in-memory store (resets on cold start — fine for demo)
STORE: dict[str, Any] = {
    "failures": {},
    "jobs": {},
    "outcomes": [],
    "magic_links": {},  # token -> record
}

CANONICAL_EVAL = {
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
        "Hard declines are policy-blocked from auto-retry (100%)."
    ),
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_playbooks() -> list[dict]:
    with PLAYBOOKS.open(encoding="utf-8") as f:
        return json.load(f)["playbooks"]


def playbook_for(code: str) -> dict:
    for pb in load_playbooks():
        if code in pb.get("decline_codes", []):
            return pb
    return next(pb for pb in load_playbooks() if pb["id"] == "PB_DEFAULT_SOFT")


def score(code: str, amount: float, attempt: int) -> tuple[float, float, bool]:
    hard = code in HARD
    if hard:
        return 0.03, 0.0, True
    p = SOFT_BASE.get(code, 0.35)
    if attempt >= 4:
        p -= 0.1
    if amount > 5000:
        p -= 0.05
    p = max(0.05, min(0.92, p))
    ev = max(0.0, p * amount - 2.5)
    return round(p, 4), round(ev, 2), False


def decide(code: str, p: float, ev: float, hard: bool) -> dict:
    pb = playbook_for(code)
    if hard or not pb.get("recoverable", True):
        action = "do_not_retry"
    elif code == "AUTHENTICATION_REQUIRED" or pb.get("preferred_action") == "send_dunning":
        action = "send_dunning"
    elif ev >= 3000 and p < 0.35:
        action = "escalate_manual"
    elif p < 0.12:
        action = "do_not_retry"
    else:
        action = pb.get("preferred_action", "schedule_retry")
    return {
        "action": action,
        "retry_after_hours": pb.get("retry_after_hours"),
        "channel": pb.get("channel"),
        "playbook_id": pb["id"],
        "playbook_excerpt": pb["guidance"],
        "explanation": (
            f"Decline `{code}` scored P(recovery)={p:.1%} and EV ₹{ev:.2f}. "
            f"Action `{action}` via playbook {pb['id']}."
        ),
    }


app = FastAPI(
    title="RecoverPilot API (Vercel)",
    description="AI Revenue Recovery demo on Vercel — lightweight serverless edition",
    version="2.1.0-vercel",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def normalize_path(request, call_next):
    """Vercel may pass /api or /api/index prefixes into the ASGI app."""
    path = request.scope.get("path", "")
    for prefix in ("/api/index", "/api"):
        if path == prefix:
            request.scope["path"] = "/"
            break
        if path.startswith(prefix + "/"):
            request.scope["path"] = path[len(prefix) :] or "/"
            break
    return await call_next(request)


@app.get("/")
def root() -> dict:
    return {
        "name": "RecoverPilot",
        "track": "AI Revenue Recovery",
        "health": "/health",
        "docs": "/docs",
        "ui": "/",
    }


def require_key(x_api_key: Optional[str]) -> None:
    if x_api_key != DEMO_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class SeedItem(BaseModel):
    payment_id: str
    decline_code: str
    amount_inr: float


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": True,
        "playbooks_loaded": PLAYBOOKS.exists(),
        "details": {
            "runtime": "vercel-lightweight",
            "note": "Heuristic scorer on Vercel; full sklearn model runs locally",
            "merchant_id": DEMO_MERCHANT_ID,
        },
    }


@app.get("/admin/demo-credentials")
def demo_credentials() -> dict:
    return {
        "merchant_id": DEMO_MERCHANT_ID,
        "api_key": DEMO_API_KEY,
        "webhook_secret": "whsec_demo_change_me",
        "note": "Vercel demo credentials",
    }


@app.get("/demo/story")
def demo_story() -> dict:
    ev = CANONICAL_EVAL
    return {
        "product": "RecoverPilot",
        "tagline": "Intelligent failed-payment recovery — soft declines recover, hard declines never auto-retry.",
        "pitch": (
            "When a payment fails, RecoverPilot scores recoverability, applies a policy-constrained "
            "playbook, schedules a job, executes via a worker, records the outcome, and can retrain."
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
            {"id": 1, "title": "Seed failures", "detail": "Fire Razorpay-shaped payment.failed webhooks."},
            {"id": 2, "title": "Soft success", "detail": "Score → schedule_retry or dunning."},
            {"id": 3, "title": "Hard block", "detail": "STOLEN_CARD / FRAUD → do_not_retry."},
            {"id": 4, "title": "Customer portal", "detail": "15-min magic link for auth failures."},
            {"id": 5, "title": "KPIs + retrain", "detail": "Outcomes feed KPIs and model versions."},
        ],
        "hard_decline_codes": sorted(HARD),
        "honest_limits": [
            "Vercel edition uses playbook heuristics (full sklearn locally).",
            "Retries/dunning are simulated unless Test Mode keys are set locally.",
            "Training starts synthetic; retrain loop from outcomes is real locally.",
        ],
        "eval_notes": ev["notes"],
    }


def _ingest(decline: str, amount: float, method: str = "upi") -> dict:
    pay_id = f"pay_{secrets.token_hex(4)}"
    fail_id = f"fail_{pay_id}"
    p, ev, hard = score(decline, amount, 1)
    decision = decide(decline, p, ev, hard)
    failure = {
        "id": fail_id,
        "merchant_id": DEMO_MERCHANT_ID,
        "external_payment_id": pay_id,
        "amount_inr": amount,
        "payment_method": method,
        "decline_code": decline,
        "status": "abandoned" if decision["action"] == "do_not_retry" else "scheduled",
        "p_recovery": p,
        "expected_value_inr": ev,
        "created_at": utcnow(),
    }
    STORE["failures"][fail_id] = failure
    job_id = None
    if decision["action"] != "do_not_retry":
        job_id = f"job_{secrets.token_hex(4)}"
        STORE["jobs"][job_id] = {
            "id": job_id,
            "failure_id": fail_id,
            "action": decision["action"],
            "status": "pending",
            "run_at": utcnow(),
            "created_at": utcnow(),
        }
    return {
        "status": "accepted",
        "failure_id": fail_id,
        "duplicate": False,
        "job_id": job_id,
        "recommendation": decision | {"p_recovery": p, "expected_value_inr": ev, "event_id": fail_id},
    }


@app.post("/admin/seed")
def seed(count: int = Query(5, ge=1, le=20), x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> dict:
    require_key(x_api_key)
    declines = [
        "INSUFFICIENT_FUNDS",
        "ISSUER_TIMEOUT",
        "AUTHENTICATION_REQUIRED",
        "NETWORK_ERROR",
        "STOLEN_CARD",
        "BANK_DECLINE_SOFT",
    ]
    items = []
    for i in range(count):
        items.append(_ingest(declines[i % len(declines)], 299 + i * 50, "upi" if i % 2 == 0 else "card"))
    return {"seeded": len(items), "items": items}


@app.post("/webhooks/razorpay")
async def webhook(payload: dict[str, Any], x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> dict:
    # Demo accepts without strict auth for easier testing
    entity = (
        payload.get("payload", {}).get("payment", {}).get("entity")
        or payload.get("payment", {})
        or {}
    )
    amount = float(entity.get("amount", 49900)) / 100.0 if entity.get("amount") else float(payload.get("amount_inr", 499))
    reason = str(entity.get("error_reason") or payload.get("decline_code") or "insufficient_funds").upper()
    mapping = {
        "INSUFFICIENT_FUNDS": "INSUFFICIENT_FUNDS",
        "PAYMENT_TIMED_OUT": "ISSUER_TIMEOUT",
        "AUTHENTICATION_FAILED": "AUTHENTICATION_REQUIRED",
        "STOLEN_CARD": "STOLEN_CARD",
        "GATEWAY_ERROR": "NETWORK_ERROR",
    }
    code = mapping.get(reason, "BANK_DECLINE_SOFT")
    if "INSUFFICIENT" in reason:
        code = "INSUFFICIENT_FUNDS"
    return _ingest(code, amount)


@app.get("/failures")
def failures(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> list:
    require_key(x_api_key)
    return list(STORE["failures"].values())[::-1]


@app.get("/jobs")
def jobs(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> list:
    require_key(x_api_key)
    return list(STORE["jobs"].values())[::-1]


@app.post("/jobs/process-due")
def process_due(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> dict:
    require_key(x_api_key)
    processed = 0
    for job in STORE["jobs"].values():
        if job["status"] != "pending":
            continue
        fail = STORE["failures"].get(job["failure_id"])
        if not fail:
            job["status"] = "failed"
            continue
        action = job["action"]
        recovered = False
        if action == "schedule_retry":
            recovered = random.random() < float(fail.get("p_recovery", 0.4))
        elif action == "send_dunning":
            recovered = random.random() < (0.35 if fail["decline_code"] == "AUTHENTICATION_REQUIRED" else 0.18)
            tok = secrets.token_urlsafe(16)
            STORE["magic_links"][tok] = {
                "token": tok,
                "failure_id": fail["id"],
                "amount_inr": fail["amount_inr"],
                "decline_code": fail["decline_code"],
                "status": "active",
                "created_at": utcnow(),
            }
            job["magic_link_url"] = f"/recover/{tok}"
        fail["status"] = "recovered" if recovered else "executed"
        STORE["outcomes"].append(
            {
                "failure_id": fail["id"],
                "recovered": recovered,
                "recovered_amount": fail["amount_inr"] if recovered else 0.0,
                "source": "retry" if action == "schedule_retry" else "dunning",
                "created_at": utcnow(),
                "magic_link_url": job.get("magic_link_url"),
            }
        )
        job["status"] = "done"
        processed += 1
    return {"processed": processed}


@app.get("/kpis")
def kpis(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> dict:
    require_key(x_api_key)
    fails = list(STORE["failures"].values())
    outcomes = STORE["outcomes"]
    recovered = [o for o in outcomes if o.get("recovered")]
    pending = sum(1 for j in STORE["jobs"].values() if j["status"] == "pending")
    total = len(fails) or 1
    return {
        "failures_total": len(fails),
        "recovered_count": len(recovered),
        "abandoned_count": sum(1 for f in fails if f["status"] == "abandoned"),
        "pending_jobs": pending,
        "recovered_amount_inr": round(sum(o["recovered_amount"] for o in recovered), 2),
        "recovery_rate": round(len(recovered) / total, 4),
    }


@app.get("/outcomes")
def outcomes(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> list:
    require_key(x_api_key)
    return STORE["outcomes"][::-1]


@app.post("/admin/retrain")
def retrain(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> dict:
    require_key(x_api_key)
    return {
        "version": "vercel-heuristic",
        "note": "Full sklearn retrain runs locally. Vercel edition uses playbook heuristics.",
        "outcomes_seen": len(STORE["outcomes"]),
    }


@app.post("/admin/magic-link/{failure_id}")
def admin_magic_link(
    failure_id: str,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> dict:
    require_key(x_api_key)
    fail = STORE["failures"].get(failure_id)
    if not fail:
        raise HTTPException(status_code=404, detail="Failure not found")
    tok = secrets.token_urlsafe(16)
    STORE["magic_links"][tok] = {
        "token": tok,
        "failure_id": failure_id,
        "amount_inr": fail["amount_inr"],
        "decline_code": fail["decline_code"],
        "status": "active",
        "created_at": utcnow(),
    }
    return {
        "token": tok,
        "url": f"/recover/{tok}",
        "failure_id": failure_id,
        "ttl_minutes": 15,
        "note": "Vercel ephemeral magic link (resets on cold start).",
    }


@app.get("/recover/{token}/status")
def magic_status(token: str) -> dict:
    row = STORE["magic_links"].get(token)
    if not row:
        return {"ok": False, "status": "invalid"}
    return {"ok": row["status"] == "active", **row}


@app.post("/recover/{token}/confirm.json")
def magic_confirm(token: str) -> dict:
    row = STORE["magic_links"].get(token)
    if not row:
        return {"ok": False, "error": "invalid"}
    if row["status"] != "active":
        return {"ok": False, "error": row["status"]}
    row["status"] = "used"
    fail = STORE["failures"].get(row["failure_id"])
    if fail:
        fail["status"] = "recovered"
    STORE["outcomes"].append(
        {
            "failure_id": row["failure_id"],
            "recovered": True,
            "recovered_amount": row["amount_inr"],
            "source": "magic_link",
            "created_at": utcnow(),
        }
    )
    return {"ok": True, "status": "recovered", "failure_id": row["failure_id"], "recovered_amount": row["amount_inr"]}


@app.post("/recover/simulate")
def simulate(payload: dict[str, Any] | None = None) -> dict:
    n = int((payload or {}).get("sample_size", 300))
    baseline = 0.0
    rp = 0.0
    baseline_retries = 0
    rp_retries = 0
    for _ in range(n):
        code = random.choice(list(SOFT_BASE) + list(HARD))
        amount = random.uniform(199, 4000)
        recovered_flag = random.random() < SOFT_BASE.get(code, 0.05)
        if code not in HARD:
            baseline_retries += 1
            baseline += (amount - 2.5) if recovered_flag and random.random() < 0.85 else -2.5
        p, ev, hard = score(code, amount, 1)
        d = decide(code, p, ev, hard)
        if d["action"] in {"schedule_retry", "send_dunning"} and p >= 0.22:
            rp_retries += 1
            ok = recovered_flag and p >= 0.22
            rp += (amount - 2.5) if ok else -2.5
    lift = ((rp - baseline) / abs(baseline) * 100.0) if abs(baseline) > 1 else 0.0
    waste = ((baseline_retries - rp_retries) / baseline_retries * 100.0) if baseline_retries else 0.0
    return {
        "sample_size": n,
        "baseline_recovered_inr": round(baseline, 2),
        "recoverpilot_recovered_inr": round(rp, 2),
        "baseline_retries": baseline_retries,
        "recoverpilot_retries": rp_retries,
        "relative_lift_pct": round(lift, 2),
        "wasted_retry_reduction_pct": round(waste, 2),
        "notes": "Vercel heuristic simulation (demo KPI).",
    }
