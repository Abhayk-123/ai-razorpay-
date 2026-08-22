# RecoverPilot
Intelligent Failed Payment Recovery Engine — Razorpay AI Buildathon  
**Track: AI Revenue Recovery**

## One-line pitch
RecoverPilot predicts which failed payments can be saved, schedules policy-constrained recovery actions, executes them via a worker, records outcomes, and can retrain from feedback.

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
pip install -r requirements.txt
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
5. Or CLI:
```bash
python -m recoverpilot.scripts.fire_webhook --count 5
python -m recoverpilot.workers.recovery_worker --once
python -m recoverpilot.ml.retrain
```

## Key APIs
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/webhooks/razorpay` | optional signature / API key | Ingest payment.failed |
| GET | `/failures` | API key | List failures |
| GET | `/jobs` | API key | List recovery jobs |
| POST | `/jobs/process-due` | API key | Run due jobs now |
| POST | `/admin/seed` | API key | Seed sample failures |
| POST | `/admin/retrain` | API key | Retrain from feedback |
| POST | `/recover/recommend` | — | Interview-style recommend |
| POST | `/recover/simulate` | — | Offline baseline comparison |

## Docker
```bash
docker compose up --build
```
Services: `api`, `worker`, `ui`

## Honest limits
- Retry/dunning execution is **local simulation** (no live card charges)
- Dataset starts **synthetic**; outcomes feed a real retrain loop
- Set `RAZORPAY_WEBHOOK_SECRET` when you plug real Test Mode webhooks later

## Project layout
```
recoverpilot/
  api/            FastAPI
  agent/          Playbooks + constrained recovery decisions
  core/           Config, DB models, auth, schemas
  integrations/   Razorpay-shaped webhooks
  ml/             Train / score / retrain
  services/       Orchestrator + pipeline
  workers/        Recovery job worker
  ui/             Streamlit ops console
  scripts/        fire_webhook helper
```

## Tests
```bash
pytest -q
```

## License
MIT — student portfolio / Buildathon submission.
