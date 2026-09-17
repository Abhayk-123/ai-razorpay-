# RecoverPilot
Intelligent Failed Payment Recovery Engine — Razorpay AI Buildathon  
**Track: AI Revenue Recovery**

## One-line pitch
When a Razorpay payment fails, RecoverPilot scores recoverability, applies a policy-constrained playbook, schedules the right action, executes via a worker (retry / dunning / escalate), offers a **15-minute magic-link customer portal**, records outcomes, and can **retrain** from feedback. Soft declines get recovered; hard declines never auto-retry.

## Proof (offline eval, n=500 synthetic)
| Metric | Value |
|--------|------:|
| RecoverPilot recovered INR | **₹1,57,262** |
| Blind soft-retry recovered INR | ₹1,29,588 |
| Relative lift | **+21.36%** |
| Hard declines auto-retried | **0 (100% blocked)** |

Source: [`artifacts/eval_summary.json`](artifacts/eval_summary.json) · live JSON: `GET /demo/story`

> Demo KPI on synthetic labels — not production causal A/B lift. Stated out loud on purpose.

## Live demo
- App UI: https://ai-razorpay.vercel.app  
- Story API: https://ai-razorpay.vercel.app/api/demo/story  
- API health: https://ai-razorpay.vercel.app/api/health  
- API docs: https://ai-razorpay.vercel.app/api/docs  

Demo API key: `rp_demo_key_change_me` (header `X-API-Key`)

> Vercel = **lightweight serverless** heuristics.  
> Full sklearn model + Streamlit + background worker = **local / Docker**.

## What it does
1. **Ingest** Razorpay-shaped `payment.failed` webhooks (HMAC-SHA256 when secret set; idempotent on event/payment id)
2. **Score** P(recovery) with a tabular model + expected value `P × amount − retry cost`
3. **Decide** via constrained playbook agent: `schedule_retry` | `send_dunning` | `escalate_manual` | `do_not_retry`
4. **Execute** via `recovery_jobs` queue + worker
5. **Customer portal** — zero-login magic link (hashed token, 15-min TTL, single-use) for dunning / auth failures
6. **Learn** — outcomes → feedback CSV → retrain (v1 → v2 → v3)

```
payment.failed webhook
        ↓
 normalize + idempotent ingest
        ↓
 ML score + playbook agent
        ↓
 recovery_jobs queue
        ↓
 worker (retry / dunning+magic-link / escalate)
        ↓
 outcomes + audit
        ↓
 feedback CSV → retrain
```

## Quick start (Windows)

### Easiest
Double-click `run_demo.bat`  
Starts **API + worker + Streamlit Ops UI**, then open the recruiter UI tips below.

### Manual
```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements-local.txt
copy .env.example .env

python -m recoverpilot.data.generate --rows 15000
python -m recoverpilot.ml.train

uvicorn recoverpilot.api.main:app --reload --port 8000
python -m recoverpilot.workers.recovery_worker --poll 2
streamlit run recoverpilot/ui/app.py
```

Open:
- Recruiter story (serve `public/index.html` or open via any static host; point API base to `http://127.0.0.1:8000`)
- Ops UI: http://127.0.0.1:8501  
- API docs: http://127.0.0.1:8000/docs  
- Demo story: http://127.0.0.1:8000/demo/story  
- Magic portal: created on dunning jobs → `/recover/{token}`

Default API key: `rp_demo_key_change_me`

## 60-second demo
1. `GET /demo/story` — show lift + hard-block %  
2. Seed 5 failures → Process due jobs  
3. Soft path → recovered / executed; hard (`STOLEN_CARD`) → abandoned, no job  
4. Auth / dunning → open magic-link portal → confirm  
5. Optional: Retrain → model version bumps  

## Razorpay Test Mode
See [`docs/RAZORPAY_TEST_MODE.md`](docs/RAZORPAY_TEST_MODE.md). Set `RAZORPAY_WEBHOOK_SECRET` and optional Test keys for payment links (`USE_RAZORPAY_PAYMENT_LINKS=true`).

## Docker
```bash
docker compose up --build
```

## Stack
FastAPI · SQLAlchemy · SQLite · scikit-learn / XGBoost · playbook RAG · Streamlit · Docker · Vercel (serverless demo)

## Honest limits
- Retries/dunning are **simulated** unless Razorpay Test Mode payment links are enabled  
- Training **starts synthetic**; retrain from outcomes is real locally  
- Vercel edition uses heuristics (bundle size); full loop is local  
- No live card charges in the default demo  

## Resume bullets
Copy-paste ready: [`docs/RESUME_BULLETS.md`](docs/RESUME_BULLETS.md)

## License
MIT — student portfolio / Buildathon submission.
