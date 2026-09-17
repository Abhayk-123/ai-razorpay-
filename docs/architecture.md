# Architecture diagram (Mermaid) — include in README demos / interviews

```mermaid
flowchart TD
  UI[Streamlit Ops / public console] --> API[FastAPI Gateway]
  WH[Razorpay payment.failed] -->|HMAC optional| API
  API --> ORCH[Pipeline Orchestrator]
  ORCH --> FEAT[Feature Builder]
  ORCH --> ML[ML Scorer P_recovery + EV]
  ORCH --> RAG[Playbook RAG]
  ORCH --> AGENT[Constrained Recovery Agent]
  AGENT -->|do_not_retry| ABANDON[Abandoned hard decline]
  AGENT -->|schedule_retry / dunning / escalate| QUEUE[recovery_jobs]
  QUEUE --> WORKER[Background Worker]
  WORKER -->|retry simulated| OUT[Outcomes + Audit]
  WORKER -->|dunning| MAGIC[Magic Link Portal 15m TTL]
  MAGIC --> OUT
  OUT --> FB[Feedback CSV]
  FB --> RETRAIN[Retrain vN]
  RETRAIN --> ML
  ML --> DB[(SQLite)]
  AGENT --> DB
  OUT --> DB
  RAG --> PB[Decline Playbooks JSON]
```

## Key contracts
- Ingest: `POST /webhooks/razorpay` (idempotent)
- Story: `GET /demo/story` (canonical proof numbers)
- Portal: `GET|POST /recover/{token}` (hashed, single-use, 15 min)
- KPIs: `GET /kpis`
- Retrain: `POST /admin/retrain`
