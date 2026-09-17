"""RecoverPilot Ops Console — production-like local control plane."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recoverpilot.core.config import API_BASE_URL, DEMO_API_KEY, SYNTHETIC_CSV
from recoverpilot.core.schemas import PaymentFailureEvent
from recoverpilot.data.generate import generate_dataset
from recoverpilot.services import orchestrator

st.set_page_config(
    page_title="RecoverPilot Ops",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

:root {
  --bg: #0b1220;
  --panel: #121a2b;
  --panel-2: #182338;
  --line: #2a3957;
  --text: #e8eefc;
  --muted: #9aabcd;
  --accent: #1ec8a5;
  --accent-2: #3d8bfd;
  --warn: #f0b429;
  --danger: #ff6b7a;
}

html, body, [class*="css"]  {
  font-family: 'IBM Plex Sans', 'DM Sans', sans-serif;
}

.stApp {
  background:
    radial-gradient(1200px 500px at 10% -10%, rgba(30,200,165,0.16), transparent 55%),
    radial-gradient(900px 420px at 90% 0%, rgba(61,139,253,0.14), transparent 50%),
    linear-gradient(180deg, #0b1220 0%, #0e1626 100%);
  color: var(--text);
}

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0e1728 0%, #101a2d 100%) !important;
  border-right: 1px solid var(--line) !important;
  min-width: 300px !important;
  width: 300px !important;
  transform: none !important;
  margin-left: 0 !important;
  visibility: visible !important;
  opacity: 1 !important;
  display: block !important;
}

section[data-testid="stSidebar"] > div {
  width: 300px !important;
}

section[data-testid="stSidebar"] * {
  color: var(--text) !important;
}

/* Keep collapse chevron available but make sidebar hard to lose */
[data-testid="stSidebarCollapsedControl"] {
  background: #122038 !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
}

.rp-side-brand {
  font-family: 'DM Sans', sans-serif;
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  margin: 0 0 0.2rem 0;
  color: #f4f7ff !important;
}
.rp-side-brand span { color: var(--accent) !important; }
.rp-side-sub { color: var(--muted) !important; font-size: 0.82rem; margin: 0 0 1rem 0; }
.rp-side-tip {
  margin-top: 0.8rem;
  padding: 0.75rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  color: var(--muted) !important;
  font-size: 0.82rem;
  background: rgba(255,255,255,0.02);
}

.rp-hero {
  padding: 1.1rem 1.35rem 1.25rem;
  border: 1px solid var(--line);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(30,200,165,0.12), rgba(61,139,253,0.08)),
    var(--panel);
  margin-bottom: 1rem;
}

.rp-brand {
  font-family: 'DM Sans', sans-serif;
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  margin: 0;
  color: #f4f7ff;
}

.rp-brand span {
  color: var(--accent);
}

.rp-sub {
  margin: 0.35rem 0 0.9rem;
  color: var(--muted);
  font-size: 0.98rem;
}

.rp-flow {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.rp-chip {
  border: 1px solid var(--line);
  background: rgba(255,255,255,0.03);
  color: #d7e2f8;
  border-radius: 999px;
  padding: 0.28rem 0.7rem;
  font-size: 0.78rem;
  font-weight: 500;
}

.rp-chip strong { color: var(--accent); }

.rp-section-title {
  font-family: 'DM Sans', sans-serif;
  font-size: 1.15rem;
  font-weight: 650;
  margin: 0.2rem 0 0.75rem;
  color: #f2f6ff;
}

.rp-card {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 14px;
  padding: 1rem 1.1rem;
  margin-bottom: 0.85rem;
}

.rp-muted { color: var(--muted); font-size: 0.9rem; }

.rp-kpi {
  border: 1px solid var(--line);
  background: linear-gradient(180deg, var(--panel-2), var(--panel));
  border-radius: 14px;
  padding: 0.9rem 1rem;
  min-height: 96px;
}

.rp-kpi .label {
  color: var(--muted);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rp-kpi .value {
  font-family: 'DM Sans', sans-serif;
  font-size: 1.55rem;
  font-weight: 700;
  margin-top: 0.25rem;
  color: #f7faff;
}

.rp-kpi .hint { color: var(--accent); font-size: 0.8rem; margin-top: 0.2rem; }

div[data-testid="stMetric"] {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.75rem 0.9rem;
}

div[data-testid="stTabs"] button[data-baseweb="tab"] {
  font-weight: 600;
}

.stButton > button {
  border-radius: 10px !important;
  font-weight: 600 !important;
}

.stButton > button[kind="primary"] {
  background: linear-gradient(90deg, #17b894, #1ec8a5) !important;
  border: none !important;
  color: #04241c !important;
}

hr { border-color: var(--line) !important; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    """
<div class="rp-hero">
  <p class="rp-brand">Recover<span>Pilot</span></p>
  <p class="rp-sub">Ops console for failed-payment recovery — score, schedule, execute, learn.</p>
  <div class="rp-flow">
    <div class="rp-chip"><strong>1</strong> webhook</div>
    <div class="rp-chip"><strong>2</strong> score</div>
    <div class="rp-chip"><strong>3</strong> job</div>
    <div class="rp-chip"><strong>4</strong> worker</div>
    <div class="rp-chip"><strong>5</strong> outcome</div>
    <div class="rp-chip"><strong>6</strong> retrain</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

if "api_key" not in st.session_state:
    st.session_state.api_key = DEMO_API_KEY

with st.sidebar:
    st.markdown(
        """
        <p class="rp-side-brand">Recover<span>Pilot</span></p>
        <p class="rp-side-sub">Ops console · AI Revenue Recovery</p>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### Connection")
    api_base = st.text_input("API base URL", API_BASE_URL)
    api_key = st.text_input("API key (X-API-Key)", st.session_state.api_key, type="password")
    st.session_state.api_key = api_key
    mode = st.radio("Recommend mode", ["HTTP API", "In-process"])
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        health_btn = st.button("Health", use_container_width=True)
    with c2:
        creds_btn = st.button("Demo key", use_container_width=True)

    if health_btn:
        try:
            h = httpx.get(f"{api_base}/health", timeout=30).json()
            st.success("API online")
            st.caption(f"Model: {'ready' if h.get('model_loaded') else 'missing'}")
        except Exception as exc:
            st.error(str(exc))
    if creds_btn:
        try:
            creds = httpx.get(f"{api_base}/admin/demo-credentials", timeout=30).json()
            st.session_state.api_key = creds["api_key"]
            st.success(f"Loaded {creds['merchant_id']}")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.markdown(
        """
        <div class="rp-side-tip">
          <b>Pages</b> are the top tabs:<br/>
          KPIs · Failures · Jobs · Fire Webhook · Recommend · Simulation · Retrain · About
          <br/><br/>
          Tip: start with <b>Fire Webhook → Seed</b>, then <b>Jobs</b>, then <b>KPIs</b>.
        </div>
        """,
        unsafe_allow_html=True,
    )


def headers() -> dict:
    return {"X-API-Key": st.session_state.api_key}


def api(method: str, path: str, **kwargs):
    with httpx.Client(timeout=120) as client:
        r = client.request(method, f"{api_base}{path}", headers=headers(), **kwargs)
        if r.status_code >= 400:
            st.error(f"{r.status_code}: {r.text}")
            r.raise_for_status()
        if r.content:
            return r.json()
        return {}


def section(title: str, blurb: str = "") -> None:
    st.markdown(f'<div class="rp-section-title">{title}</div>', unsafe_allow_html=True)
    if blurb:
        st.markdown(f'<p class="rp-muted">{blurb}</p>', unsafe_allow_html=True)


def kpi_box(label: str, value: str, hint: str = "") -> None:
    hint_html = f'<div class="hint">{hint}</div>' if hint else ""
    st.markdown(
        f"""
        <div class="rp-kpi">
          <div class="label">{label}</div>
          <div class="value">{value}</div>
          {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


tabs = st.tabs(
    [
        "KPIs",
        "Failures",
        "Jobs",
        "Fire Webhook",
        "Recommend",
        "Simulation",
        "Retrain",
        "About",
    ]
)

with tabs[0]:
    section("Live KPIs", "Snapshot of recovery performance from the local closed loop.")
    if st.button("Refresh KPIs", type="primary"):
        k = api("GET", "/kpis")
        a, b, c, d = st.columns(4)
        with a:
            kpi_box("Failures", str(k["failures_total"]))
        with b:
            kpi_box("Recovered", str(k["recovered_count"]), f"rate {k['recovery_rate']:.1%}")
        with c:
            kpi_box("Pending jobs", str(k["pending_jobs"]))
        with d:
            kpi_box("Recovered ₹", f"{k['recovered_amount_inr']:,.0f}")
        with st.expander("Raw KPI payload"):
            st.json(k)

with tabs[1]:
    section("Payment failures", "Filter and inspect ingested failed payments.")
    status = st.selectbox(
        "Status filter",
        ["", "open", "scheduled", "executed", "recovered", "abandoned"],
        format_func=lambda x: "all statuses" if x == "" else x,
    )
    if st.button("Load failures", type="primary"):
        items = api("GET", "/failures", params={"limit": 200, **({"status": status} if status else {})})
        st.session_state["failures"] = items
    items = st.session_state.get("failures")
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
    else:
        st.info("No failures loaded yet. Seed from Fire Webhook, then load here.")

with tabs[2]:
    section("Recovery jobs", "Queued retry / dunning / escalate actions.")
    jstatus = st.selectbox(
        "Job status",
        ["", "pending", "running", "done", "failed", "cancelled"],
        format_func=lambda x: "all jobs" if x == "" else x,
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Load jobs", use_container_width=True):
            jobs = api("GET", "/jobs", params={"limit": 200, **({"status": jstatus} if jstatus else {})})
            st.session_state["jobs"] = jobs
    with col_b:
        if st.button("Process due jobs now", type="primary", use_container_width=True):
            result = api("POST", "/jobs/process-due")
            st.success(f"Processed {result.get('processed', 0)} due job(s)")
    jobs = st.session_state.get("jobs")
    if jobs:
        st.dataframe(pd.DataFrame(jobs), use_container_width=True, hide_index=True)
        job_ids = [j["id"] for j in jobs]
        pick = st.selectbox("Force-run job", job_ids)
        if st.button("Run selected job"):
            st.json(api("POST", f"/jobs/{pick}/run"))
    else:
        st.info("No jobs loaded. Seed failures first, then load jobs.")

with tabs[3]:
    section("Fire webhook / seed", "Create Razorpay-shaped payment.failed events for the demo loop.")
    st.markdown('<div class="rp-card">', unsafe_allow_html=True)
    count = st.slider("How many test failures?", 1, 20, 5)
    if st.button("Seed via API", type="primary"):
        out = api("POST", f"/admin/seed?count={count}")
        st.success(f"Seeded {out.get('seeded', 0)} failure event(s)")
        with st.expander("Seed response"):
            st.json(out)
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("CLI alternative")
    st.code("python -m recoverpilot.scripts.fire_webhook --count 5", language="bash")

with tabs[4]:
    section("Explainable recommendation", "Pick a synthetic failure and see action + playbook reasoning.")
    if SYNTHETIC_CSV.exists():
        df = pd.read_csv(SYNTHETIC_CSV).sample(n=min(40, 40), random_state=3)
    else:
        df = generate_dataset(2000).sample(40, random_state=3)
    choice = st.selectbox("Synthetic event_id", df["event_id"].tolist())
    row = df[df["event_id"] == choice].iloc[0]
    ev = PaymentFailureEvent(
        event_id=row["event_id"],
        merchant_id=row["merchant_id"],
        customer_id=row["customer_id"],
        amount_inr=float(row["amount_inr"]),
        payment_method=row["payment_method"],
        issuer_bucket=row["issuer_bucket"],
        decline_code=row["decline_code"],
        attempt_number=int(row["attempt_number"]),
        hour_of_day=int(row["hour_of_day"]),
        day_of_week=int(row["day_of_week"]),
        merchant_category=row["merchant_category"],
        customer_tenure_days=int(row["customer_tenure_days"]),
        is_subscription=bool(row["is_subscription"]),
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Amount", f"₹{ev.amount_inr:,.0f}")
    m2.metric("Decline", ev.decline_code)
    m3.metric("Method", ev.payment_method)

    with st.expander("Full event payload"):
        st.json(ev.model_dump())

    if st.button("Run recommendation", type="primary"):
        if mode == "In-process":
            rec = orchestrator.recommend(ev, enqueue_job=True).model_dump()
        else:
            rec = api("POST", "/recover/recommend", json=ev.model_dump(mode="json"))
        r1, r2, r3 = st.columns(3)
        r1.metric("P(recovery)", f"{rec['p_recovery']:.1%}")
        r2.metric("Expected value", f"₹{rec['expected_value_inr']:.2f}")
        r3.metric("Action", rec["action"])
        st.info(rec.get("explanation", ""))
        st.caption(f"Playbook: {rec.get('playbook_id')} · Job: {rec.get('job_id') or 'none'}")
        with st.expander("Details"):
            st.json(rec)

with tabs[5]:
    section("Baseline vs RecoverPilot", "Offline simulation on synthetic labeled failures.")
    ss = st.slider("Sample size", 100, 2000, 400, step=100)
    if st.button("Run simulation", type="primary"):
        with st.spinner("Running simulation..."):
            if mode == "In-process":
                sim = orchestrator.simulate(ss).model_dump()
            else:
                sim = api("POST", "/recover/simulate", json={"sample_size": ss})
            st.session_state["last_sim"] = sim

    sim = st.session_state.get("last_sim")
    if not sim:
        st.info("Click **Run simulation** to see recovered-₹ comparison graphs.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            kpi_box("Blind retry ₹", f"{sim['baseline_recovered_inr']:,.0f}")
        with c2:
            kpi_box("RecoverPilot ₹", f"{sim['recoverpilot_recovered_inr']:,.0f}")
        with c3:
            kpi_box("Relative lift", f"{sim['relative_lift_pct']:.1f}%")
        st.caption(sim.get("notes", ""))

        try:
            import plotly.express as px
            import plotly.graph_objects as go

            recovered_df = pd.DataFrame(
                {
                    "Policy": ["Blind retry", "RecoverPilot"],
                    "Recovered ₹": [
                        float(sim["baseline_recovered_inr"]),
                        float(sim["recoverpilot_recovered_inr"]),
                    ],
                }
            )
            fig1 = px.bar(
                recovered_df,
                x="Policy",
                y="Recovered ₹",
                color="Policy",
                color_discrete_sequence=["#3d8bfd", "#1ec8a5"],
                title="Recovered revenue comparison",
            )
            fig1.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(18,26,43,0.6)",
                font_color="#e8eefc",
                showlegend=False,
                height=380,
            )
            st.plotly_chart(fig1, use_container_width=True)

            retries_df = pd.DataFrame(
                {
                    "Policy": ["Blind retry", "RecoverPilot"],
                    "Retries": [
                        int(sim.get("baseline_retries", 0)),
                        int(sim.get("recoverpilot_retries", 0)),
                    ],
                }
            )
            fig2 = px.bar(
                retries_df,
                x="Policy",
                y="Retries",
                color="Policy",
                color_discrete_sequence=["#3d8bfd", "#1ec8a5"],
                title="Retry count comparison (lower can mean less waste)",
            )
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(18,26,43,0.6)",
                font_color="#e8eefc",
                showlegend=False,
                height=340,
            )
            st.plotly_chart(fig2, use_container_width=True)

            lift = float(sim.get("relative_lift_pct", 0))
            waste = float(sim.get("wasted_retry_reduction_pct", 0))
            fig3 = go.Figure(
                data=[
                    go.Bar(
                        x=["Relative lift %", "Retry reduction %"],
                        y=[lift, waste],
                        marker_color=["#1ec8a5", "#f0b429"],
                    )
                ]
            )
            fig3.update_layout(
                title="Lift & wasted-retry reduction",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(18,26,43,0.6)",
                font_color="#e8eefc",
                height=320,
            )
            st.plotly_chart(fig3, use_container_width=True)
        except Exception:
            # Fallback if plotly unavailable
            chart_df = pd.DataFrame(
                {
                    "Blind retry": [sim["baseline_recovered_inr"]],
                    "RecoverPilot": [sim["recoverpilot_recovered_inr"]],
                },
                index=["Recovered ₹"],
            )
            st.bar_chart(chart_df)
            st.bar_chart(
                pd.DataFrame(
                    {
                        "Blind retry": [sim.get("baseline_retries", 0)],
                        "RecoverPilot": [sim.get("recoverpilot_retries", 0)],
                    },
                    index=["Retries"],
                )
            )

with tabs[6]:
    section("Retrain from outcomes", "Export feedback labels and bump model version.")
    if st.button("Retrain model from outcomes", type="primary"):
        metrics = api("POST", "/admin/retrain")
        st.success(f"New model version: {metrics.get('version')}")
        st.json(metrics)
    if st.button("Load outcomes"):
        outcomes = api("GET", "/outcomes")
        st.dataframe(pd.DataFrame(outcomes), use_container_width=True, hide_index=True)

with tabs[7]:
    section("About this console")
    st.markdown(
        """
<div class="rp-card">
  <p><b>Closed loop</b></p>
  <ol>
    <li>Seed / fire webhook (<code>payment.failed</code>)</li>
    <li>System scores + creates recovery job</li>
    <li>Worker executes retry/dunning (simulated locally)</li>
    <li>Outcome stored</li>
    <li>Retrain bumps model version</li>
  </ol>
  <p class="rp-muted">Demo API key comes from <code>/admin/demo-credentials</code>.</p>
  <p class="rp-muted"><b>Honest limits:</b> retries are simulated, not live Razorpay charges. Training starts synthetic; local outcomes improve the loop.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    metrics_path = ROOT / "artifacts" / "metrics.json"
    if metrics_path.exists():
        with st.expander("Current model metrics"):
            st.json(json.loads(metrics_path.read_text(encoding="utf-8")))
