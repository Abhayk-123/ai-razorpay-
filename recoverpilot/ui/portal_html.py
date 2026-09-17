"""HTML templates for the zero-login customer recovery portal."""

from __future__ import annotations

from html import escape


def portal_page(
    *,
    status: str,
    amount_inr: float | None = None,
    decline_code: str | None = None,
    expires_at: str | None = None,
    message: str | None = None,
    token: str | None = None,
) -> str:
    amount_txt = f"₹{amount_inr:,.2f}" if amount_inr is not None else "—"
    decline_txt = escape(decline_code or "—")
    expires_txt = escape(expires_at or "—")
    msg = escape(message or "")
    token_esc = escape(token or "")

    if status == "active":
        action_block = f"""
        <form method="post" action="/recover/{token_esc}/confirm">
          <button type="submit" class="primary">Confirm payment method updated</button>
        </form>
        <p class="note">Demo only — no live card charge. Confirms recovery for this single invoice.</p>
        """
    elif status == "recovered":
        action_block = f'<p class="ok">{msg or "Payment recovered. You can close this page."}</p>'
    elif status == "used":
        action_block = '<p class="warn">This link was already used.</p>'
    elif status == "expired":
        action_block = '<p class="warn">This link has expired (15-minute TTL).</p>'
    else:
        action_block = '<p class="warn">Invalid or unknown recovery link.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RecoverPilot · Update payment</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    :root {{ --bg:#0b1220; --panel:#121a2b; --line:#2a3957; --text:#e8eefc; --muted:#9aabcd; --accent:#1ec8a5; }}
    body {{ margin:0; min-height:100vh; font-family:'IBM Plex Sans',system-ui,sans-serif; color:var(--text);
      background: radial-gradient(900px 400px at 20% -10%, rgba(30,200,165,.18), transparent 55%), var(--bg);
      display:flex; align-items:center; justify-content:center; padding:1.5rem; }}
    .card {{ width:min(440px,100%); border:1px solid var(--line); background:var(--panel); border-radius:16px; padding:1.4rem 1.5rem; }}
    h1 {{ font-family:'DM Sans',sans-serif; font-size:1.35rem; margin:0 0 .35rem; letter-spacing:-.02em; }}
    h1 span {{ color:var(--accent); }}
    .sub {{ color:var(--muted); font-size:.9rem; margin:0 0 1.1rem; }}
    .row {{ display:flex; justify-content:space-between; padding:.55rem 0; border-bottom:1px solid var(--line); font-size:.92rem; }}
    .row span {{ color:var(--muted); }}
    button.primary, .primary {{ margin-top:1.1rem; width:100%; border:none; border-radius:10px; padding:.75rem 1rem;
      font-weight:600; cursor:pointer; background:linear-gradient(90deg,#17b894,#1ec8a5); color:#04241c; font-size:1rem; }}
    .note {{ color:var(--muted); font-size:.8rem; margin-top:.8rem; }}
    .ok {{ color:#7dffc8; margin-top:1rem; }}
    .warn {{ color:#ffb4bc; margin-top:1rem; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Recover<span>Pilot</span></h1>
    <p class="sub">Secure payment update · zero login · single invoice · 15-min expiry</p>
    <div class="row"><span>Amount</span><b>{amount_txt}</b></div>
    <div class="row"><span>Decline</span><b>{decline_txt}</b></div>
    <div class="row"><span>Expires</span><b>{expires_txt}</b></div>
    {action_block}
  </div>
</body>
</html>"""
