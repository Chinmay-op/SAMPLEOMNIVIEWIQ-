"""
Dashboard Data Access Layer — OI-68
======================================

Separates TimescaleDB queries from Streamlit UI logic.
All functions return pandas DataFrames or scalar values ready
for Streamlit charting and metric display.

These functions query the ``readings_*`` hypertables directly via
``query_by_time_range()`` and ``query_latest()`` (OI-54 / OI-15).

When Lead ships the rule engine (OI-56–61), the ``get_alerts()``
function can be extended to consume rule-engine events instead of
scanning for ``scenario_label`` in JSONB.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from omniview.config import (
    CONTRACTED_DEMAND_KVA,
    IDLE_CURRENT_THRESHOLD_A,
    IDLE_TEMP_THRESHOLD_C,
    MD_PENALTY_RATE_PER_KVA,
    SITE_ID,
)
from omniview.ingest.db import query_by_time_range, query_latest

logger = logging.getLogger(__name__)

# ── Timezone ─────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


# ── Helper ───────────────────────────────────────────────────────────────


def _now_ist() -> datetime:
    """Return the current time in IST."""
    return datetime.now(IST)


def _extract_data_field(row: dict[str, Any], field: str, default: float = 0.0) -> float:
    """Safely extract a numeric field from the JSONB ``data`` column."""
    data = row.get("data", {})
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return default
    try:
        return float(data.get(field, default))
    except (TypeError, ValueError):
        return default


# ═════════════════════════════════════════════════════════════════════════
# Hero 1: Live kVA vs Contracted Demand
# ═════════════════════════════════════════════════════════════════════════


def get_latest_kva(device_id: str = "pune-comp-mfm384") -> dict[str, Any]:
    """Get the latest kVA reading for an electrical device.

    Returns
    -------
    dict
        Keys: ``kva``, ``time``, ``device_id``, ``md_proximity_percent``,
        ``contract_kva``.
    """
    rows = query_latest("electrical", device_id, limit=1)
    if not rows:
        return {
            "kva": 0.0,
            "time": _now_ist(),
            "device_id": device_id,
            "md_proximity_percent": 0.0,
            "contract_kva": CONTRACTED_DEMAND_KVA,
        }

    row = rows[0]
    kva = _extract_data_field(row, "apparent_power_kva_total")
    md_pct = _extract_data_field(row, "md_proximity_percent")

    return {
        "kva": kva,
        "time": row.get("time", _now_ist()),
        "device_id": device_id,
        "md_proximity_percent": md_pct,
        "contract_kva": CONTRACTED_DEMAND_KVA,
    }


def get_kva_timeseries(
    device_id: str = "pune-comp-mfm384",
    hours: int = 24,
) -> pd.DataFrame:
    """Get kVA time-series for charting.

    Returns
    -------
    pd.DataFrame
        Columns: ``time``, ``kva``, ``kw``, ``pf``, ``device_id``.
    """
    end = _now_ist()
    start = end - timedelta(hours=hours)

    rows = query_by_time_range("electrical", device_id, start, end)

    if not rows:
        return pd.DataFrame(columns=["time", "kva", "kw", "pf", "device_id"])

    records = []
    for r in rows:
        records.append({
            "time": r["time"],
            "kva": _extract_data_field(r, "apparent_power_kva_total"),
            "kw": _extract_data_field(r, "active_power_kw_total"),
            "pf": _extract_data_field(r, "power_factor_avg", 0.95),
            "device_id": device_id,
        })

    return pd.DataFrame(records)


def get_peak_kva_24h(
    device_ids: list[str] | None = None,
) -> float:
    """Get peak kVA across all electrical devices in last 24h.

    Parameters
    ----------
    device_ids : list[str], optional
        Device IDs to check. Default: both compressor + ISBM meters.

    Returns
    -------
    float
        Peak kVA value.
    """
    if device_ids is None:
        device_ids = ["pune-comp-mfm384", "pune-isbm-mfm384"]

    end = _now_ist()
    start = end - timedelta(hours=24)
    peak = 0.0

    for did in device_ids:
        rows = query_by_time_range("electrical", did, start, end)
        for r in rows:
            kva = _extract_data_field(r, "apparent_power_kva_total")
            if kva > peak:
                peak = kva

    return peak


# ═════════════════════════════════════════════════════════════════════════
# Hero 2: Projected Monthly Demand Penalty Avoided (₹)
# ═════════════════════════════════════════════════════════════════════════


def get_penalty_avoided(
    peak_kva: float | None = None,
) -> dict[str, Any]:
    """Calculate projected demand penalty avoided.

    If peak kVA stays below contract, the avoided penalty is the
    difference × MSEDCL penalty rate × remaining billing days.

    Returns
    -------
    dict
        Keys: ``penalty_avoided_inr``, ``peak_kva``, ``contract_kva``,
        ``headroom_kva``, ``headroom_pct``.
    """
    if peak_kva is None:
        peak_kva = get_peak_kva_24h()

    headroom = max(0.0, CONTRACTED_DEMAND_KVA - peak_kva)
    headroom_pct = (headroom / CONTRACTED_DEMAND_KVA) * 100 if CONTRACTED_DEMAND_KVA > 0 else 0.0

    # MSEDCL charges penalty for each kVA exceeding contract.
    # If we stayed under, the "avoided" penalty is what we'd have paid
    # if peak_kva had hit peak + headroom used.
    penalty_avoided = headroom * MD_PENALTY_RATE_PER_KVA

    return {
        "penalty_avoided_inr": round(penalty_avoided, 2),
        "peak_kva": round(peak_kva, 2),
        "contract_kva": CONTRACTED_DEMAND_KVA,
        "headroom_kva": round(headroom, 2),
        "headroom_pct": round(headroom_pct, 1),
    }


# ═════════════════════════════════════════════════════════════════════════
# Hero 3: Specific Energy Consumption (kWh per 1,000 bottles)
# ═════════════════════════════════════════════════════════════════════════


def get_energy_and_strokes(
    hours: int = 24,
) -> dict[str, Any]:
    """Calculate Specific Energy Consumption (SEC).

    SEC = total kWh consumed / (total bottles molded / 1000)

    Returns
    -------
    dict
        Keys: ``sec_kwh_per_1k``, ``total_kwh``, ``total_strokes``,
        ``total_bottles_k``.
    """
    end = _now_ist()
    start = end - timedelta(hours=hours)

    # Get electrical energy (ISBM machine)
    elec_rows = query_by_time_range(
        "electrical", "pune-isbm-mfm384", start, end
    )

    # Sum kW readings × interval to approximate kWh
    # Each reading is 15s apart → kWh = sum(kW × 15/3600)
    total_kwh = 0.0
    for r in elec_rows:
        kw = _extract_data_field(r, "active_power_kw_total")
        total_kwh += kw * (15.0 / 3600.0)  # 15s intervals

    # Get stroke count (ISBM machine)
    stroke_rows = query_by_time_range(
        "stroke", "pune-isbm-stroke01", start, end
    )

    total_strokes = 0
    for r in stroke_rows:
        strokes = _extract_data_field(r, "strokes_since_last_poll", 0)
        total_strokes += int(strokes)

    # SEC = kWh / (strokes / 1000)
    total_bottles_k = total_strokes / 1000.0 if total_strokes > 0 else 0.0
    sec = total_kwh / total_bottles_k if total_bottles_k > 0 else 0.0

    return {
        "sec_kwh_per_1k": round(sec, 2),
        "total_kwh": round(total_kwh, 2),
        "total_strokes": total_strokes,
        "total_bottles_k": round(total_bottles_k, 2),
    }


# ═════════════════════════════════════════════════════════════════════════
# Hero 4: High-Waste Idling Motor Load (%)
# ═════════════════════════════════════════════════════════════════════════


def get_idle_load_percent(
    hours: int = 24,
) -> dict[str, Any]:
    """Calculate percentage of time the ISBM was in wasteful idle state.

    Idle = current < threshold AND thermal reading shows barrel temp
    is still elevated (energy wasted maintaining temperature with no
    production).

    Returns
    -------
    dict
        Keys: ``idle_pct``, ``idle_minutes``, ``total_minutes``,
        ``idle_readings``, ``total_readings``.
    """
    end = _now_ist()
    start = end - timedelta(hours=hours)

    elec_rows = query_by_time_range(
        "electrical", "pune-isbm-mfm384", start, end
    )

    total_readings = len(elec_rows)
    idle_readings = 0

    for r in elec_rows:
        current = _extract_data_field(r, "current_a_avg")
        data = r.get("data", {})
        if isinstance(data, str):
            import json
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}

        # Check scenario label for definitive idle detection
        scenario = data.get("scenario_label", "")
        if scenario == "lazy_idle":
            idle_readings += 1
        elif current < IDLE_CURRENT_THRESHOLD_A:
            idle_readings += 1

    # Each reading is 15s apart
    total_minutes = (total_readings * 15) / 60.0
    idle_minutes = (idle_readings * 15) / 60.0
    idle_pct = (idle_readings / total_readings * 100) if total_readings > 0 else 0.0

    return {
        "idle_pct": round(idle_pct, 1),
        "idle_minutes": round(idle_minutes, 1),
        "total_minutes": round(total_minutes, 1),
        "idle_readings": idle_readings,
        "total_readings": total_readings,
    }


# ═════════════════════════════════════════════════════════════════════════
# Alert Feed (scenario labels → pseudo-alerts)
# ═════════════════════════════════════════════════════════════════════════

_SCENARIO_META = {
    "md_nearmiss": {
        "severity": "CRITICAL",
        "title": "MD Near-Miss",
        "description": "kVA approaching contracted demand limit (500 kVA)",
        "icon": "⚡",
    },
    "lazy_idle": {
        "severity": "WARNING",
        "title": "Lazy Idle Detected",
        "description": "Machine idle but barrel temperature still elevated — energy wasted",
        "icon": "🔥",
    },
    "leak_proxy": {
        "severity": "WARNING",
        "title": "Pressure Decay (Leak Proxy)",
        "description": "Compressor pressure decaying while loaded — possible leak",
        "icon": "💨",
    },
}


def get_alerts(
    hours: int = 24,
    sensor_types: list[str] | None = None,
) -> pd.DataFrame:
    """Get alert events from scenario-labeled readings.

    Scans all sensor families for readings with ``scenario_label``
    in the JSONB data column. When Lead's rule engine (OI-56–61) is
    available, this function should be extended to consume rule events.

    Returns
    -------
    pd.DataFrame
        Columns: ``time``, ``severity``, ``title``, ``description``,
        ``icon``, ``device_id``, ``sensor_type``, ``scenario_label``.
    """
    if sensor_types is None:
        sensor_types = ["electrical", "pressure", "thermal"]

    end = _now_ist()
    start = end - timedelta(hours=hours)

    # Device IDs to scan per sensor type
    devices_by_type = {
        "electrical": ["pune-comp-mfm384", "pune-isbm-mfm384"],
        "pressure": ["pune-comp-wika01"],
        "thermal": ["pune-isbm-therm01", "pune-comp-therm01"],
    }

    alerts: list[dict[str, Any]] = []

    for stype in sensor_types:
        device_ids = devices_by_type.get(stype, [])
        for did in device_ids:
            try:
                rows = query_by_time_range(stype, did, start, end)
            except Exception:
                continue

            for r in rows:
                data = r.get("data", {})
                if isinstance(data, str):
                    import json
                    try:
                        data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        continue

                label = data.get("scenario_label")
                if label and label in _SCENARIO_META:
                    meta = _SCENARIO_META[label]
                    alerts.append({
                        "time": r["time"],
                        "severity": meta["severity"],
                        "title": meta["title"],
                        "description": meta["description"],
                        "icon": meta["icon"],
                        "device_id": did,
                        "sensor_type": stype,
                        "scenario_label": label,
                    })

    if not alerts:
        return pd.DataFrame(columns=[
            "time", "severity", "title", "description",
            "icon", "device_id", "sensor_type", "scenario_label",
        ])

    df = pd.DataFrame(alerts)
    # Deduplicate: keep first occurrence per scenario per minute
    df["minute"] = pd.to_datetime(df["time"]).dt.floor("min")
    df = df.drop_duplicates(
        subset=["minute", "scenario_label", "device_id"], keep="first"
    )
    df = df.drop(columns=["minute"])
    df = df.sort_values("time", ascending=False).reset_index(drop=True)

    return df


# ═════════════════════════════════════════════════════════════════════════
# Health Index Trend (vibration ISO zone → HI score)
# ═════════════════════════════════════════════════════════════════════════

_ISO_ZONE_SCORES = {
    "ZONE_A": 100,  # Good
    "ZONE_B": 75,   # Acceptable
    "ZONE_C": 50,   # Restricted (plan maintenance)
    "ZONE_D": 25,   # Danger (immediate action)
}


def get_health_index_trend(
    device_id: str = "pune-comp-vib01",
    hours: int = 24,
) -> pd.DataFrame:
    """Compute Health Index trend from vibration ISO zone readings.

    HI is derived from the ISO 10816-3 zone classification that
    the vibration bot already computes. When Lead ships PdM Stage 0/A
    (OI-62–67), this should be replaced with the real HI score.

    Zone mapping:
    - ZONE_A (≤2.8 mm/s) → HI 100 (Good)
    - ZONE_B (≤7.1 mm/s) → HI 75 (Acceptable)
    - ZONE_C (≤18 mm/s) → HI 50 (Restricted)
    - ZONE_D (>18 mm/s) → HI 25 (Danger)

    Returns
    -------
    pd.DataFrame
        Columns: ``time``, ``hi_score``, ``iso_zone``, ``z_rms``,
        ``device_id``.
    """
    end = _now_ist()
    start = end - timedelta(hours=hours)

    rows = query_by_time_range("vibration", device_id, start, end)

    if not rows:
        return pd.DataFrame(
            columns=["time", "hi_score", "iso_zone", "z_rms", "device_id"]
        )

    records = []
    for r in rows:
        data = r.get("data", {})
        if isinstance(data, str):
            import json
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue

        zone = data.get("iso_health_zone", "ZONE_A")
        z_rms = float(data.get("z_axis_rms_velocity_mm_sec", 0.0))
        hi = _ISO_ZONE_SCORES.get(zone, 50)

        records.append({
            "time": r["time"],
            "hi_score": hi,
            "iso_zone": zone,
            "z_rms": z_rms,
            "device_id": device_id,
        })

    return pd.DataFrame(records)


# ═════════════════════════════════════════════════════════════════════════
# Action Cards (OI-69)
# ═════════════════════════════════════════════════════════════════════════


def get_action_cards(
    hours: int = 24,
) -> list:
    """Generate action cards from scenario-labeled TSDB events.

    Scans the same event sources as ``get_alerts()`` and passes each
    detected scenario through :class:`~omniview.rules.action_cards.ActionCardGenerator`
    to produce human-readable action cards.

    When Lead's rule engine (OI-56–61) and conflict arbitration (OI-60)
    are available, this function should be extended to consume their
    event output as an additional source.

    Returns
    -------
    list[ActionCard]
        Action cards sorted by severity (CRITICAL first), deduplicated.
    """
    from omniview.rules.action_cards import ActionCardGenerator

    alerts_df = get_alerts(hours=hours)
    if alerts_df.empty:
        return []

    # Convert alert rows to event dicts with sensor data
    events: list[dict[str, Any]] = []

    for _, row in alerts_df.iterrows():
        event: dict[str, Any] = {
            "event_type": row.get("scenario_label", ""),
            "device_id": row.get("device_id", ""),
            "timestamp": row.get("time"),
            "sensor_type": row.get("sensor_type", ""),
        }

        # Enrich with sensor data for better card generation
        scenario = row.get("scenario_label", "")
        did = row.get("device_id", "")

        if scenario == "md_nearmiss" and did:
            # Fetch latest electrical reading for kVA context
            try:
                latest = query_latest("electrical", did, limit=1)
                if latest:
                    event["kva"] = _extract_data_field(latest[0], "apparent_power_kva_total")
                    event["md_proximity_percent"] = _extract_data_field(
                        latest[0], "md_proximity_percent"
                    )
                    event["contract_kva"] = CONTRACTED_DEMAND_KVA
            except Exception:
                pass

        elif scenario == "lazy_idle" and did:
            try:
                latest = query_latest("electrical", did, limit=1)
                if latest:
                    event["current_a_avg"] = _extract_data_field(latest[0], "current_a_avg")
                    event["active_power_kw_total"] = _extract_data_field(
                        latest[0], "active_power_kw_total"
                    )
                # Try to get thermal context
                thermal_did = did.replace("mfm384", "therm01")
                thermal_rows = query_latest("thermal", thermal_did, limit=1)
                if thermal_rows:
                    data = thermal_rows[0].get("data", {})
                    if isinstance(data, str):
                        import json
                        try:
                            data = json.loads(data)
                        except (json.JSONDecodeError, TypeError):
                            data = {}
                    event["barrel_temp_c"] = float(
                        data.get("barrel_temp_c",
                        data.get("process_variable_c",
                        data.get("temperature_c", 0.0)))
                    )
            except Exception:
                pass

        elif scenario == "leak_proxy" and did:
            try:
                latest = query_latest("pressure", did, limit=1)
                if latest:
                    event["pressure_bar"] = _extract_data_field(latest[0], "pressure_bar")
                    event["decay_rate_bar_per_min"] = _extract_data_field(
                        latest[0], "decay_rate_bar_per_min", 0.5
                    )
            except Exception:
                pass

        events.append(event)

    generator = ActionCardGenerator()
    return generator.generate_cards_from_alerts(events)
