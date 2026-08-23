# RecoverPilot
Intelligent Failed Payment Recovery Engine — Razorpay AI Buildathon  
**Track: AI Revenue Recovery**

## One-line pitch
RecoverPilot predicts which failed payments can be saved, schedules policy-constrained recovery actions, executes them via a worker, records outcomes, and can retrain from feedback.

## Live demo (Vercel)
- App UI: https://ai-razorpay.vercel.app  
- API health: https://ai-razorpay.vercel.app/api/health  
- API docs: https://ai-razorpay.vercel.app/api/docs  
- Project dashboard: https://vercel.com/abhayk-123s-projects/ai-razorpay  

Demo API key: `rp_demo_key_change_me`

> Vercel hosts a **lightweight serverless** demo (playbook heuristics).  
> Full sklearn model + Streamlit + background worker run **locally**.

## Production-like local loop
```
payment.failed webhook
        ↓
 normalize + idempotent ingest
        ↓
 ML score + playbook agent
        ↓
 recovery_jobs queue
        ↓
 background worker (retry / dunning / escalate)
        ↓
 outcomes + audit
        ↓
 feedback CSV → retrain (v2, v3…)
```

## Quick start (Windows)

### Easiest
Double-click `run_demo.bat`  
This starts **API + worker + Streamlit Ops UI**.

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
- Ops UI: http://127.0.0.1:8501
- API docs: http://127.0.0.1:8000/docs
- Demo credentials: http://127.0.0.1:8000/admin/demo-credentials

Default API key (local only): `rp_demo_key_change_me` (header `X-API-Key`)

## Closed-loop demo (5 minutes)
1. Ops UI → **Fire Webhook** → Seed via API  
2. **Jobs** → Process due jobs now (or wait for worker)  
3. **KPIs** / **Failures** → see recovered / abandoned  
4. **Retrain** → bump model version from outcomes  

## Docker
```bash
docker compose up --build
```

## Honest limits
- Retry/dunning execution is **simulated** (no live card charges)
- Dataset starts **synthetic**; outcomes feed a retrain loop locally
- Vercel edition uses heuristics due to serverless size limits
- Set `RAZORPAY_WEBHOOK_SECRET` when you plug real Test Mode webhooks later

## License
MIT — student portfolio / Buildathon submission.
