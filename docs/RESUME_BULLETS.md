# Resume bullets — RecoverPilot

Copy 3–4 into your resume. Keep the honest footnote for interviews.

---

## Primary (impact-first)

- Built **RecoverPilot**, a failed-payment recovery engine for the Razorpay AI Buildathon (AI Revenue Recovery): webhook ingest → ML recoverability scoring → policy-constrained playbook actions → job queue/worker → outcomes → retrain.
- Beat a blind soft-retry baseline by **~21% recovered INR** on a 500-row synthetic holdout simulation while **blocking 100% of hard declines** (stolen/fraud/invalid) from auto-retry (`artifacts/eval_summary.json`).
- Shipped a **zero-login magic-link customer portal** (SHA-256 hashed token, 15-minute TTL, single-use) so dunning/auth failures can complete recovery without an account.
- Implemented **Razorpay-shaped `payment.failed` ingest** with optional **HMAC-SHA256** verification, idempotent dedupe on event/payment id, and a Test Mode payment-link feature flag.

---

## Systems / backend depth

- Designed a production-shaped loop: FastAPI gateway, SQLAlchemy persistence, delayed `recovery_jobs`, background worker, audit log, and expected-value ranking (`P(recovery) × amount − retry cost`).
- Constrained recovery agent with four tools only (`schedule_retry`, `send_dunning`, `escalate_manual`, `do_not_retry`) grounded in JSON decline playbooks (+ optional vector RAG).

---

## One-liner for “Projects” header

**RecoverPilot** — Intelligent failed-payment recovery (FastAPI, sklearn, job worker, magic-link portal); +21% INR vs blind retry on synthetic eval; hard declines never auto-retried.

---

## Interview honesty (say this if asked)

- Default retries are **simulated** (no live charges). Razorpay **Test Mode** webhook + optional payment links are wired behind env flags.
- Training **starts synthetic**; the feedback → retrain version bump is real engineering.
- Vercel hosts a **lightweight** public demo; full sklearn + worker run locally/Docker.
