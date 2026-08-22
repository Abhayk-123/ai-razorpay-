# RecoverPilot — Demo & Interview Script (5 minutes)

## Opening (30s)
"RecoverPilot targets AI Revenue Recovery. It is a closed loop: webhook failure → ML score → scheduled recovery job → worker execution → outcome → retrain."

## Live demo (2.5 min)
1. Open Ops UI → Fire Webhook → Seed
2. Jobs → Process due jobs now
3. Failures / KPIs → recovered vs abandoned
4. Hard decline example never retries
5. Retrain → show new model version

## Architecture (1 min)
- Tabular ML for P(recovery)
- Expected value ranking
- Razorpay-shaped webhooks + idempotency
- Constrained playbook agent + job worker
- Feedback retrain loop

## Honesty (15s)
Retries are simulated locally. Data starts synthetic. Loop and engineering are real.

## Close
"Next step is plugging Razorpay Test Mode keys into the same webhook + executor interfaces."
