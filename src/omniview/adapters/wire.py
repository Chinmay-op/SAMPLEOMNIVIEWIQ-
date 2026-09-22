"""
Field-mapping adapter — OI-54 / C4
====================================

**Single source of truth** for renaming DevB's descriptive bot field names
to the short Lead/HD names consumed by Layer 3 rules and the Owner dashboard.

Contract: Layer3_Model_Layer_Technical_Architecture.md §4.1
    "Do not recompute window math in the adapter."
    "Do not invent new field names — map to the contract set."

No field renaming is allowed anywhere else in the codebase.
Run ``grep -rn`` to verify: only this module defines rename dicts.

Usage::

    from omniview.adapters.wire import adapt

    # Single reading (dict with a ``data`` sub-dict):
    adapted = adapt(raw_reading)

    # Or map just the data payload for one family:
    from omniview.adapters.wire import map_fields
    short = map_fields("electrical", raw_data_dict)
"""

from __future__ import annotations

import copy
from typing import Any

# ════════════════════════════════════════════════════════════════════════
# Per-family field maps:  DevB descriptive name  →  Lead/HD short name
#
# Rules:
#   • Every key that appears here is renamed in the output.
#   • Keys NOT in the map pass through unchanged.
#   • If a DevB bot adds a field, it passes through until someone
#     adds it here — no silent drops.
# ════════════════════════════════════════════════════════════════════════

FIELD_MAPS: dict[str, dict[str, str]] = {
    # ── Electrical (MFM384 / CT-clamp) ─────────────────────────────────
    "electrical": {
        "apparent_power_kva_total": "kva",
        "active_power_kw_total": "kw",
        "reactive_power_kvar_total": "var",
        "active_power_kw_l1": "kw_l1",
        "active_power_kw_l2": "kw_l2",
        "active_power_kw_l3": "kw_l3",
        "voltage_v_ll_avg": "voltage_ll",
        "voltage_v_l1_n": "voltage_l1",
        "voltage_v_l2_n": "voltage_l2",
        "voltage_v_l3_n": "voltage_l3",
        "current_a_avg": "current_a",
        "current_a_l1": "current_l1",
        "current_a_l2": "current_l2",
        "current_a_l3": "current_l3",
        "current_a_neutral": "current_neutral",
        "power_factor_avg": "pf",
        "power_factor_l1": "pf_l1",
        "power_factor_l2": "pf_l2",
        "power_factor_l3": "pf_l3",
        "frequency_hz": "freq_hz",
        "voltage_thd_percent": "thd_v_pct",
        "current_thd_percent": "thd_i_pct",
        "active_energy_kwh": "energy_kwh",
        "apparent_energy_kvah": "energy_kvah",
        "delta_active_energy_kwh": "delta_kwh",
        "delta_apparent_energy_kvah": "delta_kvah",
    },

    # ── Vibration (triaxial accelerometer) ─────────────────────────────
    "vibration": {
        "z_axis_rms_velocity_mm_sec": "rms_velocity_mms",
        "x_axis_rms_velocity_mm_sec": "rms_velocity_x_mms",
        "rms_velocity_mm_sec": "rms_velocity_combined_mms",
        "z_axis_peak_acceleration_g": "peak_accel_z_g",
        "x_axis_peak_acceleration_g": "peak_accel_x_g",
        "peak_acceleration_g": "peak_accel_g",
        "high_frequency_rms_acceleration_g": "hf_rms_accel_g",
        "z_axis_kurtosis": "kurtosis_z",
        "x_axis_kurtosis": "kurtosis_x",
        "z_axis_crest_factor": "crest_z",
        "x_axis_crest_factor": "crest_x",
        "peak_velocity_component_freq_hz": "peak_freq_hz",
        "temperature_c": "surface_temp_c",
        "iso_health_zone": "zone",
    },

    # ── Thermal (OMRON E5CC) ───────────────────────────────────────────
    "thermal": {
        "present_value_pv_c": "zone_temp_c",
        "set_point_sp_c": "setpoint_c",
        "manipulated_variable_mv_heat_percent": "heater_duty_pct",
        "proportional_band_p": "pid_p",
        "integral_time_i_sec": "pid_i_s",
        "derivative_time_d_sec": "pid_d_s",
        "heater_burnout_alarm_hb": "alarm_heater_burnout",
        "ssr_failure_alarm": "alarm_ssr_fail",
        "loop_burnout_alarm": "alarm_loop_burnout",
        "temperature_input_error": "alarm_input_error",
        "active_sp_number": "active_setpoint",
        "temp_trend_15min": "temp_trend_15m",
        "machine_thermal_state": "thermal_state",
    },

    # ── Pressure (WIKA / IFM transmitter) ──────────────────────────────
    "pressure": {
        "process_data_variable_raw": "raw_adc",
        "pressure_bar": "pressure_bar",          # already short — passthrough
        "pressure_unit": "unit",
        "pressure_min_memory_bar": "pressure_min_bar",
        "pressure_max_memory_bar": "pressure_max_bar",
        "teach_sp1_bar": "sp1_bar",
        "teach_sp2_bar": "sp2_bar",
        "switching_output_1_active": "sw_out_1",
        "switching_output_2_active": "sw_out_2",
        "device_status_code": "device_status",
        "internal_temperature_c": "internal_temp_c",
        "compressor_state": "compressor_state",   # passthrough
        "pressure_trend_5min": "pressure_trend_5m",
    },

    # ── Gas / switchboard overheating ──────────────────────────────────
    "gas": {
        "gas_concentration_ppm": "gas_ppm",
        "micro_particle_index": "particle_idx",
        "internal_panel_temp_c": "panel_temp_c",
        "rate_of_thermal_rise_c_per_min": "thermal_rise_rate",
        "ambient_humidity_pct": "humidity_pct",
        "air_quality_index": "aqi",
        "alert_severity_level": "severity",
    },

    # ── Stroke / production counter (IFM DI5009) ──────────────────────
    "stroke": {
        "switching_state_bdc1": "sw_bdc1",
        "switching_state_bdc2": "sw_bdc2",
        "counter_value": "cycle_count",
        "device_temperature_c": "device_temp_c",
        "operating_hours": "operating_hrs",
        "signal_quality": "signal_qual",
        "sensing_distance_margin_pct": "margin_pct",
        "device_status_code": "device_status",
        "strokes_in_interval": "strokes",
        "last_cycle_time_seconds": "cycle_time_s",
    },

    # ── Ambient (weather / environment) ────────────────────────────────
    "ambient": {
        "ambient_temp_c": "temp_c",
        "relative_humidity_pct": "humidity_pct",
        "dew_point_c": "dew_point_c",             # passthrough
        "heat_index_c": "heat_index_c",            # passthrough
        "wireless_signal_strength_dbm": "rssi_dbm",
        "environmental_baseline_offset": "baseline_offset",
    },
}

# Frozen set of families this module knows about
FAMILIES: frozenset[str] = frozenset(FIELD_MAPS.keys())


def map_fields(sensor_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Rename fields in a ``data`` dict using the family's field map.

    Unknown fields pass through unchanged.
    Unknown sensor types pass through with no renames (log a warning).
    """
    fmap = FIELD_MAPS.get(sensor_type)
    if fmap is None:
        return dict(data)  # shallow copy, no rename
    return {fmap.get(k, k): v for k, v in data.items()}


def adapt(reading: dict[str, Any]) -> dict[str, Any]:
    """Adapt a full telemetry reading (envelope + data payload).

    Returns a deep copy with the ``data`` sub-dict fields renamed.
    The envelope fields (device_id, timestamp, sensor_type, schema_version)
    are left untouched.
    """
    out = copy.deepcopy(reading)
    sensor_type = out.get("sensor_type", "")
    if "data" in out and isinstance(out["data"], dict):
        out["data"] = map_fields(sensor_type, out["data"])
    return out
