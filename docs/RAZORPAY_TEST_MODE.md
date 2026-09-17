# Razorpay Test Mode — plug into RecoverPilot

RecoverPilot already accepts Razorpay-**shaped** `payment.failed` payloads at
`POST /webhooks/razorpay` with optional **HMAC-SHA256** verification
(`X-Razorpay-Signature`). This guide wires **Test Mode** so the same path
receives Dashboard / CLI events.

## 1. Create Test Mode keys

1. Open [Razorpay Dashboard](https://dashboard.razorpay.com/) → **Test Mode**.
2. **Settings → API Keys** → generate Test Key ID + Secret (`rzp_test_…`).
3. **Settings → Webhooks** → Add webhook URL:
   - Local: use [ngrok](https://ngrok.com/) / Cloudflare Tunnel → `https://<tunnel>/webhooks/razorpay`
   - Deployed: `https://<your-host>/webhooks/razorpay`
4. Subscribe to at least `payment.failed`.
5. Copy the **Webhook secret**.

## 2. Configure `.env`

```env
RAZORPAY_WEBHOOK_SECRET=whsec_from_dashboard
RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxx
# Optional: create real Test Mode payment links on dunning instead of magic stub only
USE_RAZORPAY_PAYMENT_LINKS=true
PUBLIC_BASE_URL=https://<tunnel-or-public-origin>
API_BASE_URL=http://127.0.0.1:8000
```

Restart API + worker after changing env.

When `RAZORPAY_WEBHOOK_SECRET` is set, requests **without** a valid signature
are rejected (`401`). Live key prefixes (`rzp_live_`) are refused by the
payment-link helper on purpose.

## 3. Smoke test without Dashboard

```bash
# Seed (no Razorpay network)
curl -X POST "http://127.0.0.1:8000/admin/seed?count=3" -H "X-API-Key: rp_demo_key_change_me"

# Signed webhook (Python)
python -m recoverpilot.scripts.fire_webhook --count 1
```

With a secret set, `fire_webhook` should send `X-Razorpay-Signature` (see script).
If you POST manually, compute:

`HMAC_SHA256(webhook_secret, raw_body)` hex digest → header `X-Razorpay-Signature`.

## 4. What happens on ingest

1. Signature verified (if secret configured).
2. Payload normalized (`amount` paise → INR, error → decline code).
3. Idempotent upsert on `webhook_event_id` / `external_payment_id`.
4. ML score + playbook agent → job or `do_not_retry`.
5. Worker executes retry (simulated) or dunning (magic link ± Test payment link).

## 5. Honest limits

- Default demo **does not charge cards**. Simulated issuer response uses P(recovery).
- Payment links require Test keys + `USE_RAZORPAY_PAYMENT_LINKS=true`.
- Vercel edition is heuristic-only; full worker + sklearn run locally / Docker.

## 6. Resume line

> Ingested Razorpay `payment.failed` webhooks with HMAC-SHA256 verification and
> idempotent dedupe; Test Mode payment-link executor behind a feature flag.
