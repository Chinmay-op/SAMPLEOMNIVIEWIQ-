"""
OmniView IQ — Feature 2 "Proof of Work" Live Tester Dashboard
=============================================================

Live verification dashboard proving that all Feature 2 correlation detectors
execute against live telemetry flowing:
    MQTT → TimescaleDB → Real Detector Classes → Plotly Visualizations

Designed in strict compliance with:
- Architecture Spec: .archify/.../inputs-correlations-outputs.html
- DataViz Principles: Datawrapper Guide to Colors, Okabe-Ito Colorblind-safe palettes,
  Wilke & Tufte honest axes and direct labeling.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

from omniview.dashboard.dataviz_theme import (
    PALETTE,
    add_threshold_line,
    apply_dataviz_layout,
)
from omniview.dashboard.live_evaluator import (
    evaluate_ambient_correlation,
    evaluate_cooling_malfunction,
    evaluate_gas_model,
    evaluate_health_index_pdm,
    evaluate_lazy_idle,
    evaluate_machine_service_registry,
    evaluate_md_nearmiss,
    evaluate_pressure_leak,
    evaluate_vibration_zone,
)
from omniview.dashboard.status_inspector import evaluate_all_functions
from omniview.edge.bots.runner import get_live_bots_manager
from omniview.edge.ntp_guard import check_drift
from omniview.ingest.db import get_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OmniView IQ — Feature 2 Live Tester",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS Styling (DataViz / Minimalist Dark Theme) ──────────────────────────────
st.markdown("""
<style>
    .stApp {
        background-color: #090D16;
        color: #F8FAFC;
    }
    .main-title {
        font-size: 1.6rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 2px;
    }
    .sub-title {
        font-size: 0.9rem;
        color: #94A3B8;
        margin-bottom: 16px;
    }
    .status-badge {
        display: inline-block;
        padding: 3px 9px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .badge-live {
        background-color: rgba(0, 158, 115, 0.2);
        color: #009E73;
        border: 1px solid #009E73;
    }
    .badge-batch {
        background-color: rgba(86, 180, 233, 0.2);
        color: #56B4E9;
        border: 1px solid #56B4E9;
    }
    .badge-not-wired {
        background-color: rgba(230, 159, 0, 0.2);
        color: #E69F00;
        border: 1px solid #E69F00;
    }
    .badge-no-data {
        background-color: rgba(148, 163, 184, 0.2);
        color: #94A3B8;
        border: 1px solid #94A3B8;
    }
    .badge-not-implemented {
        background-color: rgba(213, 94, 0, 0.2);
        color: #D55E00;
        border: 1px solid #D55E00;
    }
    .panel-container {
        background-color: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 24px;
    }
    .spec-note {
        font-size: 0.8rem;
        color: #94A3B8;
        background: #1E293B;
        padding: 8px 12px;
        border-radius: 6px;
        border-left: 3px solid #56B4E9;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


# ── Sidebar Controls ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Live System Controls")

    # Time Window Selector
    time_window_choice = st.selectbox(
        "Telemetry Time Window",
        options=[
            "Live Stream (Last 15m)",
            "Last 1 Hour",
            "Last 4 Hours",
            "Full Telemetry / Historical Demo (All)",
        ],
        index=0,
    )
    lookback_minutes_map = {
        "Live Stream (Last 15m)": 15,
        "Last 1 Hour": 60,
        "Last 4 Hours": 240,
        "Full Telemetry / Historical Demo (All)": None,
    }
    chosen_lookback = lookback_minutes_map[time_window_choice]

    # Auto-Refresh
    refresh_option = st.selectbox(
        "Auto-Refresh Interval",
        options=["5 seconds", "10 seconds", "15 seconds", "Manual (Paused)"],
        index=1,
    )
    refresh_ms_map = {
        "5 seconds": 5000,
        "10 seconds": 10000,
        "15 seconds": 15000,
        "Manual (Paused)": 0,
    }
    refresh_ms = refresh_ms_map[refresh_option]

    if HAS_AUTOREFRESH and refresh_ms > 0:
        st_autorefresh(interval=refresh_ms, key="live_tester_refresher")

    st.markdown("---")

    # Bots & Ingest Daemon Manager
    st.markdown("### 🤖 Sensor Bots & Ingest")
    bot_mgr = get_live_bots_manager()
    counts = bot_mgr.get_counts()
    is_running = any(counts.values())

    if is_running:
        st.success(f"🟢 Bots Running ({sum(counts.values())} msgs sent)")
        if st.button("⏹️ Stop Live Bots"):
            bot_mgr.stop()
            st.rerun()
    else:
        st.info("⚪ Live Bots Idle")
        if st.button("▶️ Start 7 Bots + Subscriber"):
            bot_mgr.start()
            st.rerun()

    st.markdown("---")
    st.markdown("### 🕒 NTP Drift Guard")
    ntp_stat = check_drift()
    if ntp_stat.is_synced:
        st.markdown(f"**Status:** ✅ Synced (`{ntp_stat.offset_seconds:+.3f}s`)")
        st.caption(f"Server: {ntp_stat.ntp_server} | Limit: <{ntp_stat.threshold_seconds}s")
    else:
        st.error(f"❌ NTP Out of Sync: {ntp_stat.offset_seconds:.3f}s")


# ── Top Title Bar ─────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">OmniView IQ — Feature 2 Proof of Work Live Tester</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Real telemetry verification: MQTT Mosquitto → TimescaleDB → Real Layer 3 Detector Code → Accessible Plotly Analytics</div>',
    unsafe_allow_html=True,
)


# ── System Data Flow Verification Banner ──────────────────────────────────────
try:
    engine = get_engine()
    with engine.connect() as conn:
        sensor_status = []
        for s in ["electrical", "thermal", "pressure", "vibration", "gas", "stroke", "ambient"]:
            tbl = f"readings_{s}"
            cnt = conn.execute(text(f"SELECT count(*) FROM {tbl}")).scalar() or 0
            max_t = conn.execute(text(f"SELECT max(time) FROM {tbl}")).scalar()
            sensor_status.append({"Sensor": s, "Table": tbl, "Total Rows": cnt, "Latest Timestamp": str(max_t)})
    flow_df = pd.DataFrame(sensor_status)
    with st.expander("📊 TimescaleDB Live Ingestion Evidence (Click to expand)", expanded=False):
        st.dataframe(flow_df, use_container_width=True)
except Exception as e:
    st.warning(f"Could not connect to TimescaleDB: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Dynamic Implementation-Status Check
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 🔍 1. Implementation Status Summary")
statuses = evaluate_all_functions(lookback_minutes=chosen_lookback or 60)

status_rows = []
for s in statuses:
    status_rows.append({
        "Function": s.name,
        "File": s.code_file,
        "Status": s.status,
        "Reason": s.reason,
        "Latest Telemetry (UTC)": s.last_event_time,
    })
summary_table_df = pd.DataFrame(status_rows)
st.dataframe(summary_table_df, use_container_width=True)

st.markdown("---")
st.markdown("### 📈 2. Feature 2 Live Correlation Panels")


def render_status_badge(status_str: str) -> str:
    if "LIVE" in status_str and "BATCH" not in status_str:
        return f'<span class="status-badge badge-live">● {status_str}</span>'
    elif "BATCH" in status_str:
        return f'<span class="status-badge badge-batch">◆ {status_str}</span>'
    elif "NOT WIRED" in status_str:
        return f'<span class="status-badge badge-not-wired">▲ {status_str}</span>'
    elif "NO DATA" in status_str:
        return f'<span class="status-badge badge-no-data">○ {status_str}</span>'
    else:
        return f'<span class="status-badge badge-not-implemented">■ {status_str}</span>'


status_lookup = {s.name: s for s in statuses}


# ─────────────────────────────────────────────────────────────────────────────
# Panel 1: MD Near-Miss (DemandWindowDetector)
# ─────────────────────────────────────────────────────────────────────────────
fn1_status = status_lookup.get("MD Near-Miss")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("1. MD Near-Miss (15-Minute Demand Window)")
with col_badge:
    st.markdown(render_status_badge(fn1_status.status if fn1_status else "LIVE"), unsafe_allow_html=True)

st.markdown(
    '<div class="spec-note"><b>Specification Mapping:</b> Spec names file <code>md_nearmiss.py</code>, but the actual implemented code is <code>src/omniview/rules/demand_window.py</code> (<code>DemandWindowDetector</code> emitting <code>md_risk</code>).</div>',
    unsafe_allow_html=True,
)

res1 = evaluate_md_nearmiss(lookback_minutes=chosen_lookback)
df1 = res1["df"]

if not df1.empty:
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=df1["time"], y=df1["kva"],
        name="Active Demand (kVA)",
        line={"color": PALETTE["blue"], "width": 2},
        mode="lines",
    ))
    fig1.add_trace(go.Scatter(
        x=df1["time"], y=df1["projected_kva"],
        name="Projected Window Demand (kVA)",
        line={"color": PALETTE["purple"], "width": 2, "dash": "dot"},
        mode="lines",
    ))
    # Thresholds
    add_threshold_line(fig1, 500.0, "Contract Demand Cap", color=PALETTE["vermillion"])
    add_threshold_line(fig1, 450.0, "90% Near-Miss Threshold", color=PALETTE["orange"], line_dash="dashdot")

    # Event markers
    if res1["events"]:
        ev_df = pd.DataFrame(res1["events"])
        fig1.add_trace(go.Scatter(
            x=ev_df["time"], y=ev_df["projected_demand_kva"],
            mode="markers",
            marker={"size": 12, "color": PALETTE["vermillion"], "symbol": "triangle-up"},
            name="MD Risk Breach Event",
        ))

    apply_dataviz_layout(fig1, "MD Near-Miss: Real-Time kVA & Mid-Window Projections vs 500 kVA Contract", yaxis_title="Apparent Power (kVA)")
    st.plotly_chart(fig1, use_container_width=True)
else:
    st.info("No electrical telemetry found for the selected time window.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 2: Cooling Malfunction (CoolingMalfunctionDetector)
# ─────────────────────────────────────────────────────────────────────────────
fn2_status = status_lookup.get("Cooling Malfunction")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("2. Cooling Malfunction (Thermal / Energy Mismatch)")
with col_badge:
    st.markdown(render_status_badge(fn2_status.status if fn2_status else "LIVE"), unsafe_allow_html=True)

res2 = evaluate_cooling_malfunction(lookback_minutes=chosen_lookback)
df2 = res2["df"]

if not df2.empty:
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(
        go.Scatter(
            x=df2["time"], y=df2["power_kw"],
            name="Electrical Power (kW)",
            line={"color": PALETTE["blue"], "width": 2},
        ),
        secondary_y=False,
    )
    fig2.add_trace(
        go.Scatter(
            x=df2["time"], y=df2["temp_c"],
            name="Barrel / Cooling Temp (°C)",
            line={"color": PALETTE["orange"], "width": 2},
        ),
        secondary_y=True,
    )
    # Thresholds
    fig2.add_hline(y=50.0, line_dash="dash", line_color=PALETTE["vermillion"], secondary_y=False,
                   annotation_text="<b>50 kW Power Threshold</b>", annotation_position="top left")
    fig2.add_hline(y=100.0, line_dash="dash", line_color=PALETTE["sky_blue"], secondary_y=True,
                   annotation_text="<b>100 °C Low Temp Threshold</b>", annotation_position="bottom right")

    # Shaded breach regions
    breach_pts = df2[df2["breach"]]
    if not breach_pts.empty:
        fig2.add_trace(
            go.Scatter(
                x=breach_pts["time"], y=breach_pts["power_kw"],
                mode="markers",
                marker={"size": 10, "color": PALETTE["vermillion"], "symbol": "circle"},
                name="Thermal/Energy Mismatch Breach",
            ),
            secondary_y=False,
        )

    apply_dataviz_layout(fig2, "Cooling Malfunction: High Power (>50kW) alongside Cold Temp (<100°C)", yaxis_title="Active Power (kW)")
    fig2.update_yaxes(title_text="Temperature (°C)", secondary_y=True, showgrid=False)
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No paired electrical and thermal telemetry found for the selected time window.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 3: Lazy-Idle (LazyIdleDetector)
# ─────────────────────────────────────────────────────────────────────────────
fn3_status = status_lookup.get("Lazy-Idle")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("3. Lazy-Idle Waste (Unmonitored Barrel Heater Idle)")
with col_badge:
    st.markdown(render_status_badge(fn3_status.status if fn3_status else "LIVE"), unsafe_allow_html=True)

st.markdown(
    '<div class="spec-note"><b>Architectural Clarification:</b> In <code>detectors_live.py</code>, readings are evaluated per sensor without joining. Lazy-Idle requires cross-sensor data (Motor Current &lt; 0.65A AND Zone Temp &gt; 25°C). The test harness merges them chronologically to prove detector physics.</div>',
    unsafe_allow_html=True,
)

res3 = evaluate_lazy_idle(lookback_minutes=chosen_lookback)
df3 = res3["df"]

if not df3.empty:
    fig3 = make_subplots(specs=[[{"secondary_y": True}]])
    fig3.add_trace(
        go.Scatter(
            x=df3["time"], y=df3["current_a"],
            name="Motor Current (A)",
            line={"color": PALETTE["blue"], "width": 2},
        ),
        secondary_y=False,
    )
    fig3.add_trace(
        go.Scatter(
            x=df3["time"], y=df3["zone_temp_c"],
            name="Barrel Zone Temp (°C)",
            line={"color": PALETTE["orange"], "width": 2},
        ),
        secondary_y=True,
    )
    fig3.add_hline(y=0.65, line_dash="dash", line_color=PALETTE["blue"], secondary_y=False,
                   annotation_text="<b>0.65 A Idle Current Limit</b>", annotation_position="top left")
    fig3.add_hline(y=25.0, line_dash="dash", line_color=PALETTE["orange"], secondary_y=True,
                   annotation_text="<b>25 °C Heated Threshold</b>", annotation_position="bottom right")

    apply_dataviz_layout(fig3, "Lazy-Idle: Motor Idle Current (<0.65A) with Elevated Barrel Temp (>25°C)", yaxis_title="Motor Current (A)")
    fig3.update_yaxes(title_text="Temperature (°C)", secondary_y=True, showgrid=False)
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No joined current and temperature readings found for the selected time window.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 4: Pressure Leak Proxy (PressureLeakDetector)
# ─────────────────────────────────────────────────────────────────────────────
fn4_status = status_lookup.get("Pressure Leak Proxy")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("4. Pressure Leak Proxy (Loaded Decay Slope)")
with col_badge:
    st.markdown(render_status_badge(fn4_status.status if fn4_status else "LIVE"), unsafe_allow_html=True)

res4 = evaluate_pressure_leak(lookback_minutes=chosen_lookback)
df4 = res4["df"]

if not df4.empty:
    fig4 = make_subplots(specs=[[{"secondary_y": True}]])
    fig4.add_trace(
        go.Scatter(
            x=df4["time"], y=df4["pressure_bar"],
            name="Compressor Pressure (bar)",
            line={"color": PALETTE["blue"], "width": 2},
        ),
        secondary_y=False,
    )
    fig4.add_trace(
        go.Scatter(
            x=df4["time"], y=df4["decay_rate_bar_per_min"],
            name="Decay Rate (bar/min)",
            line={"color": PALETTE["vermillion"], "width": 1.5, "dash": "dot"},
        ),
        secondary_y=True,
    )
    fig4.add_hline(y=-0.15, line_dash="dash", line_color=PALETTE["vermillion"], secondary_y=True,
                   annotation_text="<b>-0.15 bar/min Leak Threshold</b>", annotation_position="bottom right")

    apply_dataviz_layout(fig4, "Pressure Leak: Loaded Pressure Discharge & Decay Rate vs -0.15 bar/min", yaxis_title="Pressure (bar)")
    fig4.update_yaxes(title_text="Decay Rate (bar/min)", secondary_y=True, showgrid=False)
    st.plotly_chart(fig4, use_container_width=True)
else:
    st.info("No pressure telemetry found for the selected time window.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 5: Vibration Zones ISO 10816-3 (VibrationZoneDetector)
# ─────────────────────────────────────────────────────────────────────────────
fn5_status = status_lookup.get("Vibration Zones (ISO 10816-3)")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("5. Vibration Zones — ISO 10816-3 RMS Velocity")
with col_badge:
    st.markdown(render_status_badge(fn5_status.status if fn5_status else "LIVE"), unsafe_allow_html=True)

res5 = evaluate_vibration_zone(lookback_minutes=chosen_lookback)
df5 = res5["df"]

if not df5.empty:
    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(
        x=df5["time"], y=df5["rms_velocity_mms"],
        name="RMS Velocity (mm/s)",
        line={"color": "#F8FAFC", "width": 2.5},
        mode="lines+markers",
    ))

    # Shaded ISO zone bands
    t_min_val, t_max_val = df5["time"].min(), df5["time"].max()
    fig5.add_hrect(y0=0.0, y1=1.4, fillcolor="rgba(0, 158, 115, 0.15)", line_width=0, annotation_text="Zone A (Good)", annotation_position="top left")
    fig5.add_hrect(y0=1.4, y1=2.8, fillcolor="rgba(86, 180, 233, 0.15)", line_width=0, annotation_text="Zone B (Acceptable)", annotation_position="top left")
    fig5.add_hrect(y0=2.8, y1=4.5, fillcolor="rgba(230, 159, 0, 0.15)", line_width=0, annotation_text="Zone C (Alert)", annotation_position="top left")
    fig5.add_hrect(y0=4.5, y1=max(6.0, df5["rms_velocity_mms"].max() + 0.5), fillcolor="rgba(213, 94, 0, 0.15)", line_width=0, annotation_text="Zone D (Danger)", annotation_position="top left")

    apply_dataviz_layout(fig5, "Vibration Zones: RMS Velocity Classified into ISO 10816-3 Bands", yaxis_title="Velocity RMS (mm/s)")
    st.plotly_chart(fig5, use_container_width=True)
else:
    st.info("No vibration telemetry found for the selected time window.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 6: Health Index & CUSUM (HealthIndexPipeline)
# ─────────────────────────────────────────────────────────────────────────────
fn6_status = status_lookup.get("Health Index & CUSUM")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("6. Health Index & CUSUM Shift Detection")
with col_badge:
    st.markdown(render_status_badge(fn6_status.status if fn6_status else "LIVE (BATCH/API)"), unsafe_allow_html=True)

st.markdown(
    '<div class="spec-note"><b>Threshold Definition:</b> High risk tier is defined as <code>HI &lt; 40</code> in <code>src/omniview/predictive/priors.py:130-131</code> and <code>src/omniview/predictive/health_index.py:230-233</code>, while <code>HI &lt; 50</code> is defined as degraded equipment in <code>src/omniview/rules/action_cards.py:360</code>. CUSUM alert threshold is <code>8.0</code>.</div>',
    unsafe_allow_html=True,
)

res6 = evaluate_health_index_pdm(machine_id="compressor-01")
df6 = res6["df"]

if not df6.empty:
    fig6 = go.Figure()
    fig6.add_trace(go.Scatter(
        x=df6["date"], y=df6["hi_score"],
        name="Health Index (0–100)",
        line={"color": PALETTE["blue"], "width": 3},
        mode="lines+markers",
    ))
    add_threshold_line(fig6, 40.0, "High Risk Tier (priors.py:130)", color=PALETTE["vermillion"])
    add_threshold_line(fig6, 50.0, "Degraded Gate (action_cards.py:360)", color=PALETTE["orange"], line_dash="dot")
    add_threshold_line(fig6, 70.0, "Medium Risk Tier", color=PALETTE["sky_blue"], line_dash="dashdot")

    apply_dataviz_layout(fig6, "Equipment Health Index (0-100) and Degradation Tiers", xaxis_title="Date", yaxis_title="Score (0–100)")
    fig6.update_yaxes(range=[0, 105])
    st.plotly_chart(fig6, use_container_width=True)
else:
    st.info("Health Index pipeline requires at least 7 daily aggregated feature rows to compute rolling slopes. (Telemetry accumulating).")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 7: Machine Service Status Registry (OI-154)
# ─────────────────────────────────────────────────────────────────────────────
fn7_status = status_lookup.get("Machine Service Status Registry")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("7. Machine Service Status Registry (OI-154)")
with col_badge:
    st.markdown(render_status_badge(fn7_status.status if fn7_status else "LIVE (BATCH/API)"), unsafe_allow_html=True)

res7 = evaluate_machine_service_registry(machine_id="compressor-01")

col_reg1, col_reg2, col_reg3 = st.columns(3)
with col_reg1:
    st.metric("Machine Monitored", res7["machine_id"])
with col_reg2:
    status_text = "IN SERVICE (SUPPRESSED)" if res7["is_in_maintenance"] else "ACTIVE (MONITORED)"
    st.metric("Service Status", status_text)
with col_reg3:
    st.metric("Registry Type", "MachineServiceRegistry (Live)")

st.markdown("""
**Cross-Feature Contract Verification:**
- **Feature 2:** Exposes `get_machine_service_status(machine_id)` returning `True` when equipment is in high-risk tier or active maintenance window.
- **Feature 3 (Demand Plan):** Excludes the machine's base load from 96-slot aggregation when service flag is `True`.
- **Feature 4 (Waste Scheduler):** Suppresses false lazy-idle electrical waste alerts while maintenance is ongoing.
""")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 8: Panel Overheat Precursor (EnhancedGasOverheatDetector)
# ─────────────────────────────────────────────────────────────────────────────
fn8_status = status_lookup.get("Panel Overheat Precursor")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("8. Panel Overheat Precursor — Gas Model & Multi-Signal Heuristics")
with col_badge:
    st.markdown(render_status_badge(fn8_status.status if fn8_status else "LIVE"), unsafe_allow_html=True)

res8 = evaluate_gas_model(lookback_minutes=chosen_lookback)
df8 = res8["df"]

if not df8.empty:
    fig8 = make_subplots(specs=[[{"secondary_y": True}]])
    fig8.add_trace(
        go.Scatter(
            x=df8["time"], y=df8["gas_ppm"],
            name="Gas Concentration (ppm)",
            line={"color": PALETTE["blue"], "width": 2},
        ),
        secondary_y=False,
    )
    fig8.add_trace(
        go.Scatter(
            x=df8["time"], y=df8["panel_temp_c"],
            name="Panel Temp (°C)",
            line={"color": PALETTE["orange"], "width": 2},
        ),
        secondary_y=True,
    )
    fig8.add_trace(
        go.Scatter(
            x=df8["time"], y=df8["micro_particle_index"],
            name="Micro-Particle Index",
            line={"color": PALETTE["purple"], "width": 1.5, "dash": "dot"},
        ),
        secondary_y=False,
    )

    apply_dataviz_layout(fig8, "Gas & Particle Overheat: Multi-Signal Gas ppm, Particles & Panel Temp", yaxis_title="Concentration / Particles")
    fig8.update_yaxes(title_text="Temperature (°C)", secondary_y=True, showgrid=False)
    st.plotly_chart(fig8, use_container_width=True)

    # Heuristic metrics
    latest_row = df8.iloc[-1]
    col_g1, col_g2, col_g3, col_g4 = st.columns(4)
    col_g1.metric("Current Tier", str(latest_row["tier"]))
    col_g2.metric("EWMA Z-Score", f"{latest_row['ewma_z_score']:.2f}")
    col_g3.metric("Root Cause", str(latest_row["root_cause"]))
    col_g4.metric("Isolation Forest Score", f"{latest_row['isolation_forest_score']:.2f} (Default prior)")
else:
    st.info("No gas telemetry found for the selected time window.")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Panel 9: Ambient Chiller OLS (AmbientCorrelationRule)
# ─────────────────────────────────────────────────────────────────────────────
fn9_status = status_lookup.get("Ambient Chiller OLS")
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.subheader("9. Ambient Chiller OLS Correlation")
with col_badge:
    st.markdown(render_status_badge(fn9_status.status if fn9_status else "NOT WIRED"), unsafe_allow_html=True)

st.markdown(
    '<div class="spec-note"><b>Wiring Status:</b> <code>AmbientCorrelationRule</code> is implemented in <code>ambient_correlation.py</code> with rolling OLS regression and dynamic 2-sigma residual gates, but is NOT wired in <code>build_default_registry()</code> in <code>detectors_live.py</code>. Executed via test harness.</div>',
    unsafe_allow_html=True,
)

res9 = evaluate_ambient_correlation(lookback_minutes=chosen_lookback)
df9 = res9["df"]

if not df9.empty:
    fig9 = make_subplots(specs=[[{"secondary_y": True}]])
    fig9.add_trace(
        go.Scatter(
            x=df9["time"], y=df9["actual_power_kw"],
            name="Actual Power (kW)",
            line={"color": PALETTE["blue"], "width": 2},
        ),
        secondary_y=False,
    )
    fig9.add_trace(
        go.Scatter(
            x=df9["time"], y=df9["expected_power_kw"],
            name="Expected Power OLS (kW)",
            line={"color": PALETTE["sky_blue"], "width": 2, "dash": "dash"},
        ),
        secondary_y=False,
    )
    fig9.add_trace(
        go.Scatter(
            x=df9["time"], y=df9["ambient_temp_c"],
            name="Ambient Temp (°C)",
            line={"color": PALETTE["orange"], "width": 1.5},
        ),
        secondary_y=True,
    )

    apply_dataviz_layout(fig9, "Ambient Correlation: Actual vs OLS Weather-Expected Power", yaxis_title="Power (kW)")
    fig9.update_yaxes(title_text="Ambient Temp (°C)", secondary_y=True, showgrid=False)
    st.plotly_chart(fig9, use_container_width=True)
else:
    st.info("No paired ambient and electrical telemetry found for the selected time window.")

