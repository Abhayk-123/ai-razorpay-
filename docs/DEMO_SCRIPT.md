# RecoverPilot — 5-Minute Demo & Interview Script

**Track:** AI Revenue Recovery (Razorpay AI Buildathon)  
**Product:** Intelligent Failed Payment Recovery Engine  

**Links (keep open before you start)**  
| What | URL |
|------|-----|
| Live UI (Vercel) | https://ai-razorpay.vercel.app |
| API health | https://ai-razorpay.vercel.app/api/health |
| API docs | https://ai-razorpay.vercel.app/api/docs |
| Local Ops UI | http://127.0.0.1:8501 *(full ML + worker)* |
| Local API docs | http://127.0.0.1:8000/docs |
| Demo API key | `rp_demo_key_change_me` (header `X-API-Key`) |

> **Tip:** For judges, prefer **local** (`run_demo.bat`) — full closed loop. Vercel = lightweight serverless demo.

---

## Minute 0:00–0:30 — Opening pitch

**Say:**

> “RecoverPilot is built for the **AI Revenue Recovery** track.  
> When a Razorpay payment fails, most systems just log it. We close the loop:  
> **webhook failure → score recoverability → schedule the right action → execute via worker → record outcome → retrain.**  
> Soft declines get recovered; hard declines are never blindly retried.”

**Show (1 slide / README diagram):**

```
payment.failed webhook
        ↓
 normalize + idempotent ingest
        ↓
 ML score + playbook agent
        ↓
 recovery_jobs queue
        ↓
 worker (retry / dunning / escalate)
        ↓
 outcomes + audit
        ↓
 feedback CSV → retrain (v2, v3…)
```

---

## Minute 0:30–1:15 — Problem + what “failure” means

**Say:**

> “Not every failure is the same. Treating them the same wastes money and annoys customers.”

| Type | Examples | What RecoverPilot does |
|------|----------|------------------------|
| **Soft / recoverable** | `INSUFFICIENT_FUNDS`, `ISSUER_TIMEOUT`, `BANK_DECLINE_SOFT`, `AUTHENTICATION_REQUIRED` | Score + playbook → **retry / dunning / escalate** |
| **Hard / do-not-retry** | `STOLEN_CARD`, `LOST_CARD`, `FRAUD_SUSPECTED`, `INVALID_CARD`, `CLOSED_ACCOUNT` | **`do_not_retry`** — no silent retry |
| **Customer action needed** | `AUTHENTICATION_REQUIRED` | **Dunning** (email/SMS CTA), not silent retry alone |
| **Transient infra** | `ISSUER_TIMEOUT`, `NETWORK_ERROR` | **Fast retry** (minutes), no customer spam |

**Say:**

> “Success for us is not ‘retry everything’. Success is **right action, right time, with policy constraints** — and proving revenue recovered vs abandoned.”

---

## Minute 1:15–3:30 — Live demo (closed loop)

### A) Seed failures (webhook path) — ~30s

**Do:** Ops UI → **Fire Webhook** → Seed via API  
*(or CLI: `python -m recoverpilot.scripts.fire_webhook --count 5`)*

**Say:**

> “This fires Razorpay-**shaped** `payment.failed` events. Ingest is **idempotent** — same event twice won’t double-create jobs.”

**Point at:** Failures list filling up with decline codes, amounts, merchant.

---

### B) Soft failure → SUCCESS path — ~45s

**Do:** Open a soft decline (`INSUFFICIENT_FUNDS` / `ISSUER_TIMEOUT`).

**Say:**

> “Here’s a **soft failure**. ML gives P(recovery) and expected value after retry cost.  
> The constrained agent picks a playbook — for insufficient funds, delayed silent retry around 24–48h; for issuer timeout, a quick retry.”

**Do:** Jobs → **Process due jobs now** (or wait for background worker).

**Say:**

> “The worker executes: retry, dunning, or escalate. Outcome is written — **recovered** or not — into audit + feedback.”

**Point at:** Status → `recovered` / recovered amount; KPI bump.

---

### C) Hard failure → SAFE / NO-RETRY path — ~30s

**Do:** Find / seed a hard decline (`STOLEN_CARD`, `FRAUD_SUSPECTED`, etc.).

**Say:**

> “This is the important **failure guardrail**. Hard declines are marked non-recoverable.  
> Preferred action is **`do_not_retry`**. We do **not** burn retries or risk fraud amplification.  
> That’s intentional — revenue recovery without policy is just bad automation.”

**Point at:** No retry job / abandoned or do-not-retry decision in explanation.

---

### D) KPIs — recovered vs abandoned — ~20s

**Do:** Open **KPIs** / Failures summary.

**Say:**

> “Judges care about measurable recovery:  
> - failures ingested  
> - **recovered count + recovered INR**  
> - **abandoned** (including hard declines / exhausted attempts)  
> - recovery rate  
> That’s the dashboard for revenue impact.”

---

### E) Retrain loop — ~30s

**Do:** Ops UI → **Retrain** *(or `python -m recoverpilot.ml.retrain`)*

**Say:**

> “Outcomes go to feedback CSV. Retrain bumps the model version — v1 → v2 → v3.  
> So the system doesn’t just predict once; it **learns from what actually recovered**.”

**Point at:** New `model_version` / metrics in artifacts.

---

## Minute 3:30–4:20 — Architecture (what we built)

**Say (keep short, point at code or diagram):**

| Layer | What |
|-------|------|
| **Ingest** | FastAPI + Razorpay-shaped webhooks, optional signature, API key auth |
| **Features + ML** | Tabular model → P(recovery), expected value ranking (revenue − retry cost) |
| **Agent** | Decline playbooks (JSON) + constrained decisions — not free-form LLM spend |
| **Execution** | `recovery_jobs` queue + background worker |
| **Memory / audit** | SQLite outcomes, explanations, KPIs |
| **Ops** | Streamlit console for seed, jobs, KPIs, retrain |
| **Deploy** | Docker locally; Vercel serverless for public API/UI demo |

**One line:**

> “It’s production-*shaped*: gateway, queue, worker, feedback — not a single notebook demo.”

---

## Minute 4:20–4:45 — Honesty (buildathon trust)

**Say:**

> “Being clear on limits:  
> 1. Retries / dunning are **simulated** — we don’t charge live cards.  
> 2. Training data **starts synthetic**; the retrain loop from outcomes is real.  
> 3. Vercel hosts a **lightweight** demo; full sklearn + Streamlit + worker run **locally**.  
> Same webhook and executor interfaces are ready for Razorpay **Test Mode** keys.”

---

## Minute 4:45–5:00 — Close

**Say:**

> “RecoverPilot turns payment failures into a **measurable recovery system**:  
> soft failures get smart recovery, hard failures get blocked, outcomes feed the next model.  
> Next step: plug Razorpay Test Mode webhook secret into the same `/webhooks/razorpay` path and swap the simulated executor for Test Mode APIs.  
> Happy to deep-dive on ML features, playbooks, or idempotency.”

**Leave on screen:** KPIs (recovered vs abandoned) + live health URL.

---

## Q&A cheat sheet (if judges ask)

| Question | Short answer |
|----------|--------------|
| Why not retry everything? | Hard declines / fraud → never auto-retry; cost + risk. |
| How do you rank jobs? | P(recovery) × amount − retry cost → expected value. |
| What if webhook duplicates? | Idempotent ingest on event/payment id. |
| Is the agent an LLM? | Constrained playbook agent (+ optional RAG over playbooks); decisions are policy-bound. |
| What is “success”? | Soft decline → recovered amount + status `recovered`. |
| What is “failure” (product sense)? | Hard decline abandoned, exhausted retries, or low-EV skip — not all red statuses are bugs. |
| Local vs Vercel? | Local = full loop; Vercel = public serverless demo. |
| Demo key? | `rp_demo_key_change_me` via `X-API-Key`. |

---

## Click path checklist (local, before demo)

1. [ ] `run_demo.bat` → API + worker + Streamlit up  
2. [ ] http://127.0.0.1:8501 opens  
3. [ ] Seed 5 webhooks  
4. [ ] Process due jobs  
5. [ ] Soft decline shows recovered path  
6. [ ] Hard decline shows do-not-retry  
7. [ ] KPIs updated  
8. [ ] Retrain bumps version  
9. [ ] Optional: open https://ai-razorpay.vercel.app for “also deployed” proof  

**Backup if UI fails:** API docs → `POST /admin/seed` → `POST /jobs/process-due` → `GET /kpis`

---

## Spoken-only script (read aloud, ~5 minutes)

*Keep Ops UI open. Click while you speak. Don’t read the stage directions out loud.*

---

**[0:00 — Opening]**

RecoverPilot is built for the AI Revenue Recovery track.

When a Razorpay payment fails, most systems just log it and move on. We close the loop.

A failed payment webhook comes in. We score how recoverable it is. We schedule the right action. A worker executes it. We record the outcome. And we retrain from that feedback.

So soft declines can be recovered — and hard declines are never blindly retried.

---

**[0:30 — Problem]**

Not every failure is the same.

If the bank says insufficient funds, a delayed retry can bring the money back.  
If there is an issuer timeout, a quick retry often works.  
If the customer needs authentication, silent retry alone usually fails — we need a dunning message.  
But if the card is stolen, lost, or fraud is suspected — we must never auto-retry.

Success for us is not “retry everything.”  
Success is the right action, at the right time, with policy constraints — and measurable recovered revenue versus abandoned failures.

---

**[1:15 — Live demo: seed]**

Let me show the closed loop live.

I am seeding Razorpay-shaped payment-failed events into the system.  
Ingest is idempotent — the same event twice will not create duplicate jobs.

You can see failures coming in with decline codes, amounts, and merchant context.

---

**[1:45 — Soft failure → success]**

Here is a soft failure — for example insufficient funds or issuer timeout.

The model estimates probability of recovery and expected value after retry cost.  
A constrained playbook agent chooses the action — delayed silent retry, fast retry, or dunning.

Now I process due jobs. The worker runs.

When recovery succeeds, status becomes recovered, recovered amount is recorded, and KPIs update.  
That is the success path.

---

**[2:30 — Hard failure → guardrail]**

Now the important failure case.

This is a hard decline — stolen card, fraud suspected, invalid card, closed account.  
Preferred action is do not retry.

We intentionally do not burn retries and we do not amplify fraud risk.  
Revenue recovery without policy is just bad automation.  
So this path shows abandoned or blocked — by design.

---

**[3:00 — KPIs + retrain]**

On the dashboard you can see the business view: failures ingested, recovered count, recovered amount in rupees, abandoned count, and recovery rate.

Outcomes also go into feedback.  
When I hit retrain, the model version bumps — v1 to v2 to v3.  
So the system does not only predict once. It learns from what actually recovered.

---

**[3:30 — Architecture]**

Under the hood this is production-shaped.

FastAPI is the gateway for webhooks and APIs.  
We build features, score with tabular ML, and rank by expected value.  
A playbook agent makes constrained decisions — not free-form spend.  
Jobs go to a queue and a background worker executes retry, dunning, or escalate.  
Everything is audited in SQLite, with a Streamlit ops console.  
It also runs in Docker locally, and we have a public Vercel demo for the API.

---

**[4:20 — Honesty]**

I want to be clear on limits.

Retries and dunning are simulated — we do not charge live cards.  
Training data starts synthetic, but the retrain loop from real outcomes is real.  
Vercel hosts a lightweight public demo. The full model, Streamlit UI, and worker run locally.  
The same webhook and executor interfaces are ready for Razorpay Test Mode keys.

---

**[4:45 — Close]**

So RecoverPilot turns payment failures into a measurable recovery system:  
soft failures get smart recovery, hard failures get blocked, and outcomes feed the next model.

Next step is plugging Razorpay Test Mode into the same webhook path and swapping the simulated executor for Test Mode APIs.

Happy to deep-dive on the ML features, the playbooks, or idempotency. Thank you.

---

### Ultra-short backup (if only ~90 seconds)

RecoverPilot closes the loop on failed payments: webhook in, score recoverability, schedule the right action, worker executes, outcome recorded, model retrains.

Soft declines like insufficient funds get recovered with smart retries or dunning.  
Hard declines like stolen or fraud are never auto-retried.

Here is live seed → process jobs → recovered KPI — and here a hard decline blocked by policy.  
Retrain bumps the model version from feedback.

Simulated retries, synthetic start data, real engineering loop — ready for Razorpay Test Mode next.
