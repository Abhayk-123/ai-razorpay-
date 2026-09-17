# RecoverPilot — Full Speaking Script (How to Speak)

**Total time:** ~5 minutes  
**Rule:** Bold text = speak aloud. *Italic* = do on screen, do not speak.

Before you start, open:
- Local Ops UI: http://127.0.0.1:8501
- Optional proof: https://ai-razorpay.vercel.app

Breathe. Speak slower than you think. Pause after every important sentence.

---

## PART 1 — Opening (0:00 to 0:40)

**Hello everyone. My name is Abhay, and this is RecoverPilot.**

**RecoverPilot is built for the Razorpay AI Buildathon, under the AI Revenue Recovery track.**

**The problem is simple. When a payment fails, most systems only log the failure and stop. That means lost revenue.**

**RecoverPilot closes the loop.**

**A payment-failed webhook comes in.**  
**We score how recoverable that failure is.**  
**We schedule the right recovery action.**  
**A background worker executes it.**  
**We record the outcome.**  
**And we retrain the model from that feedback.**

**So soft declines can be recovered — and hard declines are never blindly retried.**

*Point at the flow on screen / README diagram for 3 seconds. Pause.*

---

## PART 2 — What failure and success mean (0:40 to 1:20)

**Before I demo, I want to define failure and success clearly.**

**Not every payment failure is the same.**

**If the decline is insufficient funds, a delayed retry can bring the money back. That can become a success.**

**If there is an issuer timeout or network error, a quick retry often works.**

**If authentication is required, silent retry alone usually fails. In that case we send dunning — a customer message with a payment update link.**

**But if the card is stolen, lost, fraud is suspected, or the account is closed — that is a hard decline. We must never auto-retry.**

**So success for RecoverPilot is not “retry everything.”**

**Success means: the right action, at the right time, under policy constraints — and measurable recovered revenue versus abandoned failures.**

*Short pause. Smile. Transition.*

---

## PART 3 — Live demo: seed failures (1:20 to 1:50)

**Let me show the closed loop live.**

*Go to Ops UI → Fire Webhook → Seed (or Seed via API). Wait for rows.*

**I am now seeding Razorpay-shaped payment-failed events into the system.**

**These look like real Razorpay webhook payloads, so the same path can later accept Test Mode webhooks.**

**Ingest is idempotent. If the same event arrives twice, we do not create duplicate recovery jobs.**

*Point at Failures list.*

**Here you can see failures coming in — with decline codes, amounts, and merchant context.**

---

## PART 4 — Soft failure → SUCCESS path (1:50 to 2:45)

*Open one soft decline row: INSUFFICIENT_FUNDS or ISSUER_TIMEOUT.*

**This one is a soft failure — recoverable.**

**Our ML model estimates the probability of recovery.**  
**Then we compute expected value: how much revenue we might recover, minus retry cost.**

**A constrained playbook agent chooses the action.**  
**For insufficient funds, that is usually a delayed silent retry.**  
**For issuer timeout, that is usually a fast retry.**  
**For authentication required, that is dunning, not silent retry alone.**

*Go to Jobs → Process due jobs now.*

**Now I process the due jobs. The background worker executes the action.**

*Wait for status update. Point at recovered status / amount.*

**When recovery succeeds, the status becomes recovered.**  
**The recovered amount is stored.**  
**And the KPIs update.**

**This is the success path — a failed payment turned back into revenue.**

---

## PART 5 — Hard failure → SAFE path (2:45 to 3:25)

*Open / find a hard decline: STOLEN_CARD, FRAUD_SUSPECTED, INVALID_CARD, CLOSED_ACCOUNT.*

**Now the important failure case.**

**This is a hard decline.**

**The preferred action is do not retry.**

**We intentionally do not schedule silent retries here.**  
**We do not burn money on useless attempts.**  
**And we do not amplify fraud risk.**

**Revenue recovery without policy is just bad automation.**

*Point at do_not_retry / abandoned / blocked decision.*

**So this path is blocked by design. That is also a correct outcome — not a bug.**

---

## PART 6 — KPIs and retrain (3:25 to 4:00)

*Open KPIs page.*

**This is the business view judges care about.**

**You can see how many failures were ingested.**  
**How many were recovered.**  
**How much recovered amount in rupees.**  
**How many were abandoned.**  
**And the overall recovery rate.**

*Click Retrain. Wait for version bump.*

**Outcomes also go into a feedback file.**  
**When I retrain, the model version bumps — for example from version one to version two.**

**That means RecoverPilot does not only predict once.**  
**It learns from what actually recovered in the real loop.**

---

## PART 7 — Architecture in 40 seconds (4:00 to 4:40)

**Under the hood, this is production-shaped engineering.**

**FastAPI is the gateway for webhooks and APIs.**  
**We build features and score with a tabular ML model.**  
**We rank jobs by expected value.**  
**A playbook agent makes constrained decisions — not free-form guessing.**  
**Jobs go into a queue, and a worker executes retry, dunning, or escalate.**  
**Everything is audited in SQLite.**  
**Operators use a Streamlit console.**

**It runs with Docker locally.**  
**And we also deployed a public demo on Vercel for the API and lightweight UI.**

*Optional: briefly show https://ai-razorpay.vercel.app*

---

## PART 8 — Honesty (4:40 to 4:55)

**I want to be honest about limits.**

**Retries and dunning are simulated. We do not charge live cards.**  
**Training data starts synthetic.**  
**But the closed loop — ingest, score, schedule, execute, outcome, retrain — is real.**  
**Vercel hosts a lightweight public demo.**  
**The full model, Streamlit UI, and worker run locally.**

**The same webhook and executor interfaces are ready for Razorpay Test Mode keys.**

---

## PART 9 — Close (4:55 to 5:10)

**To summarize:**

**RecoverPilot turns payment failures into a measurable recovery system.**  
**Soft failures get smart recovery.**  
**Hard failures get blocked.**  
**Outcomes feed the next model.**

**Next step is plugging Razorpay Test Mode into the same webhook path, and swapping the simulated executor for Test Mode APIs.**

**Thank you. I am happy to take questions on the ML features, the playbooks, or idempotency.**

*Stop. Smile. Hands still. Wait for questions.*

---

## If you get only 90 seconds — say ONLY this

**RecoverPilot closes the loop on failed payments: webhook in, score recoverability, schedule the right action, worker executes, customer can finish via a 15-minute magic link, outcome recorded, model retrains.**

*Seed → process jobs.*

**On a 500-failure offline eval we recovered about 21% more INR than blind soft retry, and we blocked 100% of hard declines from auto-retry.**

*Show hard decline.*

**Here a hard decline is blocked — we never auto-retry fraud or stolen cards.**

*Show KPIs / story numbers.*

**Soft declines get smart retries or dunning with a customer portal. Retries are simulated today unless Razorpay Test Mode is plugged in; the engineering loop is real. Thank you.**

---

## How to speak (delivery tips)

1. **Speed:** Speak at about 120–130 words per minute. If you rush, slow down on “soft” and “hard.”
2. **Emphasis words:** say these slower and clearer — *closed loop*, *soft decline*, *hard decline*, *do not retry*, *recovered*, *retrain*.
3. **Never apologize** on stage (“sorry UI is slow”). Just wait quietly.
4. **If a click fails:** say — **“I will show the same flow through the API docs.”** Then open `/docs` → seed → process-due → kpis.
5. **Eye contact:** look at judges after each part title (Opening, Soft success, Hard block, Close).
6. **One finger rule:** point at one thing on screen at a time.

---

## Practice checklist (say out loud once)

- [ ] Opening pitch without looking at notes  
- [ ] Soft success while clicking Process due jobs  
- [ ] Hard decline + “do not retry” line  
- [ ] KPIs + retrain line  
- [ ] Honesty + close  
- [ ] 90-second backup once
