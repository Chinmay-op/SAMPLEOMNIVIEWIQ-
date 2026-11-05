"""
OmniView IQ — Live Evaluator Engine for Feature 2 Tester
=========================================================

Extracts raw telemetry from TimescaleDB, applies wire adapters, and feeds
real detector classes to extract:
  (a) Input signals over time
  (b) Detector internal values vs configured thresholds
  (c) Fired events and anomaly markers
  (d) Execution metrics and diagnostics
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

from omniview.adapters.wire import adapt
from omniview.config import (
    CONTRACTED_DEMAND_KVA,
    COOLING_POWER_THRESHOLD_KW,
    COOLING_TEMP_LOW_C,
    LAZY_IDLE_DURATION_MIN,
    LAZY_IDLE_RULE_CURRENT_A,
    LAZY_IDLE_RULE_TEMP_C,
    MD_ALERT_MINUTE,
    PRESSURE_DECAY_THRESHOLD_BAR_PER_MIN,
    VIB_ZONE_B_BOUNDARY,
    VIB_ZONE_C_BOUNDARY,
    VIB_ZONE_D_BOUNDARY,
)
from omniview.ingest.db import get_engine
from omniview.predictive.batch_runner import HealthIndexPipeline
from omniview.predictive.maintenance_log import MaintenanceLogger, MaintenanceEvent
from omniview.rules.ambient_correlation import AmbientCorrelationRule
from omniview.rules.cooling_malfunction import CoolingMalfunctionDetector
from omniview.rules.demand_window import DemandWindowDetector
from omniview.rules.gas_model import EnhancedGasOverheatDetector
from omniview.rules.lazy_idle import LazyIdleDetector
from omniview.rules.predictive_maintenance import (
    MachineServiceRegistry,
    get_machine_service_status,
)
from omniview.rules.pressure_leak import PressureLeakDetector
from omniview.rules.vibration_zone import VibrationZoneDetector, classify_zone

logger = logging.getLogger(__name__)


def query_tsdb_series(sensor_type: str, limit: int = 200, lookback_minutes: int | None = None) -> list[dict[str, Any]]:
    """Query TimescaleDB for raw readings ordered chronologically (oldest to newest)."""
    table = f"readings_{sensor_type}"
    engine = get_engine()
    readings = []

    try:
        with engine.connect() as conn:
            if lookback_minutes is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
                query = text(f"""
                    SELECT time, device_id, site_id, sensor_type, data
                    FROM {table}
                    WHERE time >= :cutoff
                    ORDER BY time ASC
                    LIMIT :limit
                """)
                rows = conn.execute(query, {"cutoff": cutoff, "limit": limit}).fetchall()
            else:
                # Get the most recent N rows and sort chronologically
                query = text(f"""
                    SELECT time, device_id, site_id, sensor_type, data
                    FROM {table}
                    ORDER BY time DESC
                    LIMIT :limit
                """)
                rows = conn.execute(query, {"limit": limit}).fetchall()
                rows = list(reversed(rows))

            for r in rows:
                data_val = r.data
                if isinstance(data_val, str):
                    try:
                        data_val = json.loads(data_val)
                    except Exception:
                        data_val = {}
                readings.append({
                    "time": r.time,
                    "timestamp": r.time.isoformat() if hasattr(r.time, "isoformat") else str(r.time),
                    "device_id": r.device_id,
                    "site_id": r.site_id,
                    "sensor_type": r.sensor_type,
                    "data": data_val,
                })
    except Exception as e:
        logger.warning("TSDB query error for %s: %s", sensor_type, e)

    return readings


# ─────────────────────────────────────────────────────────────────────────────
# 1. MD Near-Miss (DemandWindowDetector)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_md_nearmiss(lookback_minutes: int | None = None, limit: int = 150) -> dict[str, Any]:
    raw_readings = query_tsdb_series("electrical", limit=limit, lookback_minutes=lookback_minutes)
    detector = DemandWindowDetector()

    series = []
    events = []

    for r in raw_readings:
        adapted = adapt(r)
        event = detector.evaluate(adapted)

        # Extract values
        data = adapted.get("data", {})
        kva = float(data.get("kva", data.get("apparent_power_kva_total", 0.0)))
        accum_kva_min = float(detector._accumulated)
        
        # Calculate elapsed minutes in current window
        ts = detector._parse_timestamp(adapted)
        elapsed_min = (ts - detector._window_start).total_seconds() / 60.0 if detector._window_start else 0.0
        time_remaining = max(0, detector._window_min - elapsed_min)
        projected_kva = (accum_kva_min + kva * time_remaining) / detector._window_min if elapsed_min > 0 else kva

        entry = {
            "time": r["time"],
            "kva": kva,
            "accumulated_kva_minutes": accum_kva_min,
            "projected_kva": projected_kva,
            "t_minutes": elapsed_min,
            "contract_limit": CONTRACTED_DEMAND_KVA,
            "alert_minute": MD_ALERT_MINUTE,
        }
        series.append(entry)

        if event:
            events.append({
                "time": r["time"],
                "projected_demand_kva": event.projected_demand_kva,
                "accumulated_kva_minutes": event.accumulated_kva_minutes,
                "t_minutes": event.t_minutes,
                "severity": event.severity,
            })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "events": events,
        "contract_limit": CONTRACTED_DEMAND_KVA,
        "alert_minute": MD_ALERT_MINUTE,
        "detector_state": {
            "window_start": str(detector._window_start),
            "accumulated_kva_minutes": round(detector._accumulated, 2),
            "peak_kva": round(detector._peak_kva, 2),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cooling Malfunction (CoolingMalfunctionDetector)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_cooling_malfunction(lookback_minutes: int | None = None, limit: int = 150) -> dict[str, Any]:
    elec_readings = query_tsdb_series("electrical", limit=limit, lookback_minutes=lookback_minutes)
    therm_readings = query_tsdb_series("thermal", limit=limit, lookback_minutes=lookback_minutes)

    detector = CoolingMalfunctionDetector()
    events = []
    series = []

    # Merge chronologically
    combined = []
    for r in elec_readings:
        combined.append((r["time"], "electrical", r))
    for r in therm_readings:
        combined.append((r["time"], "thermal", r))
    combined.sort(key=lambda x: x[0])

    for t, stype, r in combined:
        adapted = adapt(r)
        # Normalize device_id to the monitored machine asset
        adapted["device_id"] = "isbm-01"
        event = detector.evaluate(adapted)

        st = detector._state.get("isbm-01", {})
        kw = st.get("power_kw")
        temp = st.get("temp_c")

        if kw is not None and temp is not None:
            breach = (kw > COOLING_POWER_THRESHOLD_KW) and (temp < COOLING_TEMP_LOW_C)
            series.append({
                "time": t,
                "power_kw": kw,
                "temp_c": temp,
                "breach": breach,
                "power_threshold": COOLING_POWER_THRESHOLD_KW,
                "temp_threshold": COOLING_TEMP_LOW_C,
            })

        if event:
            events.append({
                "time": t,
                "power_kw": event.active_power_kw,
                "cooling_temp_c": event.cooling_temp_c,
                "action_suggestion": event.action_suggestion,
            })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "events": events,
        "power_threshold": COOLING_POWER_THRESHOLD_KW,
        "temp_threshold": COOLING_TEMP_LOW_C,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Lazy-Idle (LazyIdleDetector + Test Harness Cross-Sensor Join)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_lazy_idle(lookback_minutes: int | None = None, limit: int = 150) -> dict[str, Any]:
    elec_readings = query_tsdb_series("electrical", limit=limit, lookback_minutes=lookback_minutes)
    therm_readings = query_tsdb_series("thermal", limit=limit, lookback_minutes=lookback_minutes)

    detector = LazyIdleDetector()
    events = []
    series = []

    # Harness join: Maintain rolling forward-fill of current and temperature
    combined = []
    for r in elec_readings:
        combined.append((r["time"], "electrical", adapt(r)))
    for r in therm_readings:
        combined.append((r["time"], "thermal", adapt(r)))
    combined.sort(key=lambda x: x[0])

    cur_current = None
    cur_temp = None

    for t, stype, sample in combined:
        data = sample.get("data", {})
        if stype == "electrical":
            cur_current = float(data.get("current_a", data.get("current_a_avg", 0.0)))
        elif stype == "thermal":
            cur_temp = float(data.get("zone_temp_c", data.get("present_value_pv_c", 0.0)))

        if cur_current is not None and cur_temp is not None:
            # Joined sample passed to LazyIdleDetector
            joined_sample = {
                "device_id": sample.get("device_id", "compressor-01"),
                "timestamp": t.isoformat() if hasattr(t, "isoformat") else str(t),
                "data": {
                    "current_a": cur_current,
                    "zone_temp_c": cur_temp,
                },
            }
            event = detector.evaluate(joined_sample)
            condition = (cur_current < LAZY_IDLE_RULE_CURRENT_A) and (cur_temp > LAZY_IDLE_RULE_TEMP_C)

            series.append({
                "time": t,
                "current_a": cur_current,
                "zone_temp_c": cur_temp,
                "condition": condition,
                "current_threshold": LAZY_IDLE_RULE_CURRENT_A,
                "temp_threshold": LAZY_IDLE_RULE_TEMP_C,
            })

            if event:
                events.append({
                    "time": t,
                    "current_a": event.current_a,
                    "zone_temp_c": event.zone_temp_c,
                    "duration_min": event.duration_min,
                })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "events": events,
        "current_threshold": LAZY_IDLE_RULE_CURRENT_A,
        "temp_threshold": LAZY_IDLE_RULE_TEMP_C,
        "duration_min": LAZY_IDLE_DURATION_MIN,
        "harness_joined": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pressure Leak Proxy (PressureLeakDetector)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_pressure_leak(lookback_minutes: int | None = None, limit: int = 150) -> dict[str, Any]:
    raw_readings = query_tsdb_series("pressure", limit=limit, lookback_minutes=lookback_minutes)
    detector = PressureLeakDetector()

    series = []
    events = []

    for r in raw_readings:
        adapted = adapt(r)
        event = detector.evaluate(adapted)

        data = adapted.get("data", {})
        pressure_bar = float(data.get("pressure_bar", 0.0))
        comp_state = data.get("compressor_state", "LOADED")
        loaded = (comp_state == "LOADED") or bool(data.get("loaded", True))

        # Query internal slope buffer
        decay_rate = 0.0
        buf = detector._buffers.get(r.get("device_id", "compressor-01"), deque())
        if len(buf) >= 2:
            dt_min = (buf[-1][0] - buf[0][0]) / 60.0
            if dt_min > 0:
                decay_rate = (buf[-1][1] - buf[0][1]) / dt_min

        series.append({
            "time": r["time"],
            "pressure_bar": pressure_bar,
            "loaded": 1 if loaded else 0,
            "decay_rate_bar_per_min": decay_rate,
            "threshold": -PRESSURE_DECAY_THRESHOLD_BAR_PER_MIN,
        })

        if event:
            events.append({
                "time": r["time"],
                "pressure_bar": event.pressure_bar,
                "decay_rate": event.decay_rate_bar_per_min,
            })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "events": events,
        "decay_threshold": -PRESSURE_DECAY_THRESHOLD_BAR_PER_MIN,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Vibration Zones (VibrationZoneDetector)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_vibration_zone(lookback_minutes: int | None = None, limit: int = 150) -> dict[str, Any]:
    raw_readings = query_tsdb_series("vibration", limit=limit, lookback_minutes=lookback_minutes)
    detector = VibrationZoneDetector()

    series = []
    events = []

    for r in raw_readings:
        adapted = adapt(r)
        event = detector.evaluate(adapted)

        data = adapted.get("data", {})
        rms_vel = float(data.get("rms_velocity_mms", data.get("z_axis_rms_velocity_mm_sec", 0.0)))
        zone = data.get("zone") or classify_zone(rms_vel)

        series.append({
            "time": r["time"],
            "rms_velocity_mms": rms_vel,
            "zone": zone,
            "zone_b": VIB_ZONE_B_BOUNDARY,
            "zone_c": VIB_ZONE_C_BOUNDARY,
            "zone_d": VIB_ZONE_D_BOUNDARY,
        })

        if event:
            events.append({
                "time": r["time"],
                "rms_velocity_mms": event.rms_velocity_mms,
                "zone": event.zone,
                "prev_zone": event.prev_zone,
            })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "events": events,
        "boundaries": {
            "zone_b": VIB_ZONE_B_BOUNDARY,
            "zone_c": VIB_ZONE_C_BOUNDARY,
            "zone_d": VIB_ZONE_D_BOUNDARY,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Health Index & CUSUM (Predictive Maintenance Batch Pipeline)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_health_index_pdm(machine_id: str = "compressor-01", days_limit: int = 30) -> dict[str, Any]:
    """Execute HealthIndexPipeline driven from TSDB electrical + vibration telemetry."""
    pipeline = HealthIndexPipeline()
    elec_raw = query_tsdb_series("electrical", limit=15000)

    # Format readings into pipeline contract
    readings = []
    for r in elec_raw:
        readings.append({"time": r["time"], "timestamp": r["timestamp"], "data": r["data"]})

    batch_result = pipeline.run_batch(
        machine_id=machine_id,
        electrical_readings=readings,
    )

    series = []
    for i, hi in enumerate(batch_result.hi_series):
        slope_row = batch_result.slopes[i] if i < len(batch_result.slopes) else {}

        series.append({
            "date": hi.date,
            "hi_score": hi.health_index,
            "risk_tier": hi.risk_tier,
            "vibration_slope_7d": slope_row.get("z_rms_slope_7d") or slope_row.get("current_slope_7d", 0.0),
            "high_risk_threshold": 40.0,   # Defined in priors.py:130-131 & health_index.py:230-233
            "action_card_threshold": 50.0, # Defined in action_cards.py:360
        })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "batch_result": batch_result,
        "events": batch_result.events,
        "cusum_alerts": batch_result.cusum_alerts,
        "latest_hi": batch_result.latest_hi,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Machine Service Status Registry (OI-154)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_machine_service_registry(machine_id: str = "compressor-01") -> dict[str, Any]:
    registry = MachineServiceRegistry.get_instance()
    is_in_maintenance = get_machine_service_status(machine_id)
    history = registry._latest_hi

    m_logger = MaintenanceLogger()
    try:
        logged_events = m_logger.read_all()
    except Exception:
        logged_events = []

    return {
        "machine_id": machine_id,
        "is_in_maintenance": is_in_maintenance,
        "active_records_count": len(history) if isinstance(history, dict) else (1 if history else 0),
        "history": history,
        "logged_events": logged_events,
        "registry_type": "In-Memory Dynamic Registry + MaintenanceLogger Facade",
        "has_persistence": len(logged_events) > 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Panel Overheat Precursor (EnhancedGasOverheatDetector)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_gas_model(lookback_minutes: int | None = None, limit: int = 150) -> dict[str, Any]:
    raw_readings = query_tsdb_series("gas", limit=limit, lookback_minutes=lookback_minutes)
    detector = EnhancedGasOverheatDetector()

    series = []
    events = []

    for r in raw_readings:
        event = detector.evaluate(r)

        data = r.get("data", {})
        gas_ppm = float(data.get("gas_concentration_ppm", 0.0))
        part_idx = float(data.get("micro_particle_index", 0.0))
        panel_temp = float(data.get("internal_panel_temp_c", 0.0))
        rise_rate = float(data.get("rate_of_thermal_rise_c_per_min", 0.0))

        # Query internal EWMA state for gas_ppm
        dev_id = r.get("device_id", "compressor-01")
        ewma_map = detector._ewma.get(dev_id, {})
        z_score = 0.0
        if "gas_ppm" in ewma_map:
            tracker = ewma_map["gas_ppm"]
            z_score = float(tracker._last_z) if tracker._last_z is not None else 0.0

        tier = "NORMAL"
        root_cause = "NORMAL_OPERATION"
        confidence = 100.0

        if event:
            tier = getattr(event, "tier", "CRITICAL")
            root_cause = getattr(event, "root_cause", "ELECTRICAL_OVERLOAD")
            confidence = getattr(event, "confidence_score", 85.0)
            events.append({
                "time": r["time"],
                "tier": tier,
                "root_cause": root_cause,
                "confidence_score": confidence,
            })

        series.append({
            "time": r["time"],
            "gas_ppm": gas_ppm,
            "micro_particle_index": part_idx,
            "panel_temp_c": panel_temp,
            "rate_of_thermal_rise_c_per_min": rise_rate,
            "ewma_z_score": z_score,
            "tier": tier,
            "root_cause": root_cause,
            "confidence": confidence,
            "isolation_forest_score": 0.0,  # Baseline prior default (unsupervised cluster)
        })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "events": events,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Ambient Chiller OLS (AmbientCorrelationRule)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_ambient_correlation(lookback_minutes: int | None = None, limit: int = 150) -> dict[str, Any]:
    amb_readings = query_tsdb_series("ambient", limit=limit, lookback_minutes=lookback_minutes)
    elec_readings = query_tsdb_series("electrical", limit=limit, lookback_minutes=lookback_minutes)

    rule = AmbientCorrelationRule(min_readings=3, window_size=60)
    events = []
    series = []

    # Merge chronologically
    combined = []
    for r in amb_readings:
        combined.append((r["time"], "ambient", r))
    for r in elec_readings:
        combined.append((r["time"], "electrical", adapt(r)))
    combined.sort(key=lambda x: x[0])

    cur_amb = None
    cur_kw = None

    for t, stype, sample in combined:
        data = sample.get("data", {})
        if stype == "ambient":
            cur_amb = float(data.get("ambient_temp_c", 25.0))
        elif stype == "electrical":
            cur_kw = float(data.get("kw", data.get("active_power_kw_total", 0.0)))

        if cur_amb is not None and cur_kw is not None:
            event = rule.evaluate(ambient_temp_c=cur_amb, active_power_kw=cur_kw)

            series.append({
                "time": t,
                "ambient_temp_c": cur_amb,
                "actual_power_kw": cur_kw,
                "expected_power_kw": event.expected_power_kw,
                "residual_kw": event.residual_kw,
                "residual_sigma": event.residual_sigma,
                "event_type": event.event_type,
            })

            if event.event_type in ("COOLING_LOAD_HIGH", "COOLING_LOAD_LOW"):
                events.append({
                    "time": t,
                    "event_type": event.event_type,
                    "residual_kw": event.residual_kw,
                    "residual_sigma": event.residual_sigma,
                    "message": event.message,
                })

    df = pd.DataFrame(series)
    return {
        "df": df,
        "events": events,
        "sigma_threshold": 2.0,
    }
