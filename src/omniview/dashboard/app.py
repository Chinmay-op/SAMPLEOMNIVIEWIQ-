"""
OmniView IQ — Live Dashboard (OI-68)
========================================

Streamlit dashboard fulfilling PRD FR8: live hero metrics, kVA vs
contracted demand chart, alert feed, and Health Index trend.

Run::

    streamlit run src/omniview/dashboard/app.py

Or from the repo root::

    python -m streamlit run src/omniview/dashboard/app.py

Requires seeded data (OI-55) or live TSDB data from the subscriber.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from omniview.config import (
    CONTRACTED_DEMAND_KVA,
    DASHBOARD_REFRESH_S,
    SITE_ID,
)
from omniview.dashboard.queries import (
    get_alerts,
    get_energy_and_strokes,
    get_health_index_trend,
    get_idle_load_percent,
    get_kva_timeseries,
    get_latest_kva,
    get_penalty_avoided,
)

logger = logging.getLogger(__name__)

# ── Page config ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="OmniView IQ — Live Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ───────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Hero metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
    }
    div[data-testid="stMetric"] label {
        color: #a8b2d1 !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #e6f1ff !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }

    /* Main header */
    .main-header {
        background: linear-gradient(135deg, #0f3460 0%, #533483 100%);
        padding: 20px 30px;
        border-radius: 16px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(83, 52, 131, 0.3);
    }
    .main-header h1 {
        color: #e6f1ff !important;
        margin: 0 !important;
        font-size: 1.8rem !important;
    }
    .main-header p {
        color: #a8b2d1 !important;
        margin: 4px 0 0 0 !important;
        font-size: 0.95rem !important;
    }

    /* Section headers */
    .section-header {
        color: #ccd6f6 !important;
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #233554;
        padding-bottom: 8px;
        margin-top: 16px;
    }

    /* Alert severity badges */
    .alert-critical {
        background-color: #e74c3c;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .alert-warning {
        background-color: #f39c12;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Dark theme override */
    .stApp {
        background-color: #0a192f;
    }
    header[data-testid="stHeader"] {
        background-color: #0a192f;
    }
</style>
""", unsafe_allow_html=True)


# ── Header ───────────────────────────────────────────────────────────────

st.markdown(f"""
<div class="main-header">
    <h1>⚡ OmniView IQ — ISBM-PET Pune</h1>
    <p>Live Dashboard · Site: {SITE_ID} · Contract: {CONTRACTED_DEMAND_KVA} kVA · Auto-refresh: {DASHBOARD_REFRESH_S}s</p>
</div>
""", unsafe_allow_html=True)


# ── Hero Metrics Row ─────────────────────────────────────────────────────

def _render_hero_metrics() -> None:
    """Render the 4 PRD §2.6 hero metrics as Streamlit metric cards."""

    col1, col2, col3, col4 = st.columns(4)

    # Hero 1: Live kVA vs Contract
    with col1:
        try:
            kva_data = get_latest_kva()
            kva = kva_data["kva"]
            pct = (kva / CONTRACTED_DEMAND_KVA * 100) if CONTRACTED_DEMAND_KVA > 0 else 0
            delta_label = f"{pct:.0f}% of {CONTRACTED_DEMAND_KVA} kVA"
            st.metric(
                label="⚡ Live kVA",
                value=f"{kva:.1f}",
                delta=delta_label,
                delta_color="inverse",  # red when high
            )
        except Exception as e:
            st.metric(label="⚡ Live kVA", value="—")
            logger.warning("Hero 1 error: %s", e)

    # Hero 2: ₹ Penalty Avoided
    with col2:
        try:
            penalty = get_penalty_avoided()
            avoided = penalty["penalty_avoided_inr"]
            headroom = penalty["headroom_pct"]
            st.metric(
                label="💰 Penalty Avoided",
                value=f"₹{avoided:,.0f}",
                delta=f"{headroom:.0f}% headroom",
                delta_color="normal",
            )
        except Exception as e:
            st.metric(label="💰 Penalty Avoided", value="—")
            logger.warning("Hero 2 error: %s", e)

    # Hero 3: SEC (kWh / 1,000 bottles)
    with col3:
        try:
            sec_data = get_energy_and_strokes()
            sec = sec_data["sec_kwh_per_1k"]
            bottles_k = sec_data["total_bottles_k"]
            st.metric(
                label="🏭 SEC (kWh/1k bottles)",
                value=f"{sec:.1f}" if sec > 0 else "—",
                delta=f"{bottles_k:.1f}k bottles today",
                delta_color="off",
            )
        except Exception as e:
            st.metric(label="🏭 SEC", value="—")
            logger.warning("Hero 3 error: %s", e)

    # Hero 4: Idle Load %
    with col4:
        try:
            idle = get_idle_load_percent()
            idle_pct = idle["idle_pct"]
            idle_min = idle["idle_minutes"]
            st.metric(
                label="🔥 Idle Load",
                value=f"{idle_pct:.1f}%",
                delta=f"{idle_min:.0f} min wasted",
                delta_color="inverse",
            )
        except Exception as e:
            st.metric(label="🔥 Idle Load", value="—")
            logger.warning("Hero 4 error: %s", e)


_render_hero_metrics()

st.divider()

# ── kVA vs Contract Chart ───────────────────────────────────────────────

st.markdown('<p class="section-header">📊 kVA vs Contracted Demand (24h)</p>', unsafe_allow_html=True)


def _render_kva_chart() -> None:
    """Render the kVA time-series with contract limit line."""

    try:
        # Get data for both electrical meters
        df_comp = get_kva_timeseries("pune-comp-mfm384", hours=24)
        df_isbm = get_kva_timeseries("pune-isbm-mfm384", hours=24)

        frames = []
        if not df_comp.empty:
            df_comp["source"] = "Compressor"
            frames.append(df_comp)
        if not df_isbm.empty:
            df_isbm["source"] = "ISBM"
            frames.append(df_isbm)

        if not frames:
            st.info("No electrical data available. Run the seed script: `python -m omniview.ingest.seed`")
            return

        df = pd.concat(frames, ignore_index=True)
        df["time"] = pd.to_datetime(df["time"])

        # Add contract limit line
        df["Contract Limit (kVA)"] = CONTRACTED_DEMAND_KVA

        # Pivot for multi-line chart
        chart_data = df.pivot_table(
            index="time", columns="source", values="kva", aggfunc="first"
        )
        chart_data["Contract (500 kVA)"] = CONTRACTED_DEMAND_KVA

        st.line_chart(chart_data, use_container_width=True, height=350)

    except Exception as e:
        st.error(f"Could not load kVA chart: {e}")
        logger.error("kVA chart error: %s", e)


_render_kva_chart()

st.divider()

# ── Alerts + HI Trend (side by side) ────────────────────────────────────

col_alerts, col_hi = st.columns([1, 1])

# Alert Feed
with col_alerts:
    st.markdown('<p class="section-header">🔔 Alert Feed</p>', unsafe_allow_html=True)

    try:
        alerts_df = get_alerts(hours=24)

        if alerts_df.empty:
            st.info("No alerts in the last 24 hours.")
        else:
            # Show summary counts
            crit_count = len(alerts_df[alerts_df["severity"] == "CRITICAL"])
            warn_count = len(alerts_df[alerts_df["severity"] == "WARNING"])

            acol1, acol2, acol3 = st.columns(3)
            with acol1:
                st.metric("Total", len(alerts_df))
            with acol2:
                st.metric("🔴 Critical", crit_count)
            with acol3:
                st.metric("🟡 Warning", warn_count)

            # Show alert table
            display_df = alerts_df[["time", "icon", "title", "severity", "device_id"]].copy()
            display_df.columns = ["Time", "", "Alert", "Severity", "Device"]
            display_df["Time"] = pd.to_datetime(display_df["Time"]).dt.strftime("%H:%M")
            st.dataframe(
                display_df.head(20),
                use_container_width=True,
                hide_index=True,
            )

    except Exception as e:
        st.error(f"Could not load alerts: {e}")
        logger.error("Alert feed error: %s", e)

# Health Index Trend
with col_hi:
    st.markdown('<p class="section-header">📈 Health Index — Compressor</p>', unsafe_allow_html=True)

    try:
        hi_df = get_health_index_trend("pune-comp-vib01", hours=24)

        if hi_df.empty:
            st.info("No vibration data available for HI trend.")
        else:
            # Current HI
            latest_hi = hi_df.iloc[-1]["hi_score"]
            latest_zone = hi_df.iloc[-1]["iso_zone"]

            zone_colors = {
                "ZONE_A": "🟢", "ZONE_B": "🟡",
                "ZONE_C": "🟠", "ZONE_D": "🔴",
            }
            zone_icon = zone_colors.get(latest_zone, "⚪")

            hcol1, hcol2 = st.columns(2)
            with hcol1:
                st.metric("Current HI", f"{latest_hi}/100")
            with hcol2:
                st.metric("ISO Zone", f"{zone_icon} {latest_zone}")

            # HI trend chart
            hi_chart = hi_df[["time", "hi_score"]].copy()
            hi_chart["time"] = pd.to_datetime(hi_chart["time"])
            hi_chart = hi_chart.set_index("time")
            st.line_chart(hi_chart, use_container_width=True, height=250)

    except Exception as e:
        st.error(f"Could not load HI trend: {e}")
        logger.error("HI trend error: %s", e)

# ── Action Cards (OI-69) ────────────────────────────────────────────────

st.divider()

try:
    from omniview.dashboard.action_card_ui import render_action_cards_section
    from omniview.dashboard.queries import get_action_cards

    action_cards = get_action_cards(hours=24)
    render_action_cards_section(action_cards)
except Exception as e:
    st.markdown('<p class="section-header">🎯 Action Cards</p>', unsafe_allow_html=True)
    st.error(f"Could not load action cards: {e}")
    logger.error("Action cards error: %s", e)
    action_cards = []

# ── Alert Routing Log (OI-71) ───────────────────────────────────────

st.divider()

try:
    from omniview.config import ALERT_ROUTING_ENABLED, ALERT_WEBHOOK_URL
    from omniview.dashboard.alert_router import AlertRouter

    st.markdown(
        '<p class="section-header">🔔 Alert Routing Log</p>',
        unsafe_allow_html=True,
    )

    if not ALERT_ROUTING_ENABLED:
        st.info("Alert routing is disabled (set ALERT_ROUTING_ENABLED=true in .env)")
    elif not action_cards:
        st.info(
            "No alerts to route. Routing activates when action cards "
            "are generated from rule/PdM events."
        )
    else:
        router = AlertRouter(
            enabled=ALERT_ROUTING_ENABLED,
            webhook_url=ALERT_WEBHOOK_URL,
        )
        routing_results = router.route_batch(action_cards)

        if routing_results:
            # Summary row
            rcol1, rcol2, rcol3, rcol4 = st.columns(4)
            with rcol1:
                st.metric("Total Dispatches", len(routing_results))
            with rcol2:
                webhook_count = sum(
                    1 for r in routing_results if r.channel.value == "webhook"
                )
                st.metric("🌐 Webhook", webhook_count)
            with rcol3:
                email_count = sum(
                    1 for r in routing_results if r.channel.value == "email"
                )
                st.metric("📧 Email", email_count)
            with rcol4:
                log_count = sum(
                    1 for r in routing_results if r.channel.value == "log"
                )
                st.metric("📝 Log", log_count)


            routing_data = []
            for r in routing_results:
                channel_icons = {
                    "webhook": "🌐", "email": "📧", "log": "📝",
                    "sms": "📱", "cmms": "🎫",
                }
                routing_data.append({
                    "Time": r.timestamp.strftime("%H:%M:%S"),
                    "Channel": f"{channel_icons.get(r.channel.value, '📤')} {r.channel.value.upper()}",
                    "Target": r.target_role.replace("_", " ").title(),
                    "Status": "✅" if r.status == "sent" else "❌",
                    "Detail": r.detail[:80],
                })

            st.dataframe(
                pd.DataFrame(routing_data),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No routing dispatches yet.")

except Exception as e:
    st.markdown(
        '<p class="section-header">🔔 Alert Routing Log</p>',
        unsafe_allow_html=True,
    )
    st.error(f"Could not load routing log: {e}")
    logger.error("Alert routing log error: %s", e)

# ── Jumbo Floor Display (OI-72) ─────────────────────────────────────

st.divider()

try:
    from omniview.dashboard.jumbo_display import JumboDisplayFeed

    st.markdown(
        '<p class="section-header">📺 Jumbo Floor Display — Register Feed</p>',
        unsafe_allow_html=True,
    )

    feed = JumboDisplayFeed(data_source="mock")
    snapshot = feed.update()
    drift = feed.check_drift()

    # Display key values as the operator would see them
    jcol1, jcol2, jcol3, jcol4 = st.columns(4)
    with jcol1:
        st.metric(
            "⚡ Live kVA",
            f"{snapshot.live_kva:.1f}",
            delta=f"{snapshot.md_proximity_pct:.0f}% of contract",
            delta_color="inverse",
        )
    with jcol2:
        sev_labels = {0: "✅ None", 1: "🔵 Info", 2: "🟡 Warning", 3: "🔴 Critical"}
        st.metric("🚨 Severity", sev_labels.get(snapshot.active_severity, "—"))
    with jcol3:
        st.metric("🟡 Warnings", snapshot.warning_count)
    with jcol4:
        drift_label = "✅ Synced" if not drift.drifted else f"⚠️ Drift {drift.max_drift_pct:.2f}%"
        st.metric("🔄 Drift Check", drift_label)

    with st.expander("📋 Register Bank (16 holding registers)"):
        reg_data = []
        reg_names = {
            0: "live_kva (H)", 1: "live_kva (L)",
            2: "contract_kva (H)", 3: "contract_kva (L)",
            4: "md_proximity (H)", 5: "md_proximity (L)",
            6: "penalty_avoided (H)", 7: "penalty_avoided (L)",
            8: "idle_load_pct (H)", 9: "idle_load_pct (L)",
            10: "warning_count", 11: "critical_count",
            12: "active_severity", 13: "heartbeat",
            14: "peak_kva_24h (H)", 15: "peak_kva_24h (L)",
        }
        for addr in range(16):
            reg_data.append({
                "Addr": addr,
                "Name": reg_names.get(addr, "—"),
                "Value": snapshot.registers.get(addr, 0),
                "Hex": f"0x{snapshot.registers.get(addr, 0):04X}",
            })
        st.dataframe(
            pd.DataFrame(reg_data),
            use_container_width=True,
            hide_index=True,
        )

except Exception as e:
    st.markdown(
        '<p class="section-header">📺 Jumbo Floor Display</p>',
        unsafe_allow_html=True,
    )
    st.error(f"Could not load jumbo display: {e}")
    logger.error("Jumbo display error: %s", e)


# ── Footer ───────────────────────────────────────────────────────────

st.divider()
st.caption(
    f"OmniView IQ · Site: {SITE_ID} · Contract: {CONTRACTED_DEMAND_KVA} kVA · "
    f"Dashboard refreshes every {DASHBOARD_REFRESH_S}s · "
    f"Data: seeded (OI-55) + live (subscriber)"
)

# ── Auto-refresh ─────────────────────────────────────────────────────────
# Streamlit doesn't have built-in auto-refresh, but we can use
# st.rerun with a sleep timer via the sidebar.

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    auto_refresh = st.toggle("Auto-refresh", value=False)
    refresh_interval = st.slider(
        "Refresh interval (seconds)",
        min_value=10,
        max_value=120,
        value=DASHBOARD_REFRESH_S,
    )
    hours_window = st.slider(
        "Time window (hours)",
        min_value=1,
        max_value=72,
        value=24,
    )

    if auto_refresh:
        import time
        time.sleep(refresh_interval)
        st.rerun()
