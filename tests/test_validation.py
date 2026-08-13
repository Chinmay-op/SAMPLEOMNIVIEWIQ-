import pytest
from omniview.ingest.validation import validate_payload


# ── Valid payload matching real electrical_schema.json ────────────────────
_VALID_ELECTRICAL = {
    "device_id": "Selec-MFM384-01",
    "timestamp": "2026-08-13T17:00:00Z",
    "sensor_type": "electrical_meter",
    "data": {
        "voltage_v_ln_avg": 239.5,
        "voltage_v_ll_avg": 414.8,
        "current_a_avg": 205.3,
        "active_power_kw_total": 140.2,
        "apparent_power_kva_total": 147.6,
        "reactive_power_kvar_total": 45.8,
        "power_factor_avg": 0.949,
        "frequency_hz": 50.02,
        "active_energy_kwh": 150042.5,
        "apparent_energy_kvah": 157544.6,
        "rolling_kva_15min": 148.1,
        "md_proximity_percent": 29.6,
    },
}


def test_validate_payload_valid_electrical():
    assert validate_payload("electrical", "1.0", _VALID_ELECTRICAL) is True


def test_validate_payload_missing_required():
    # Missing device_id — a required top-level field
    payload = {
        "timestamp": "2026-08-13T17:00:00Z",
        "sensor_type": "electrical_meter",
        "data": _VALID_ELECTRICAL["data"],
    }
    assert validate_payload("electrical", "1.0", payload) is False


def test_validate_payload_wrong_type():
    # device_id as int instead of string
    payload = {**_VALID_ELECTRICAL, "device_id": 12345}
    assert validate_payload("electrical", "1.0", payload) is False


def test_validate_payload_vibration():
    # Vibration now has a real schema — valid payload should pass
    payload = {
        "device_id": "Banner-QM30VT1-01",
        "timestamp": "2026-08-13T17:00:00Z",
        "sensor_type": "vibration_node",
        "data": {
            "z_axis_rms_velocity_mm_sec": 2.1,
            "x_axis_rms_velocity_mm_sec": 1.5,
            "z_axis_peak_acceleration_g": 0.45,
            "x_axis_peak_acceleration_g": 0.33,
            "high_frequency_rms_acceleration_g": 0.38,
            "temperature_c": 42.5,
            "iso_health_zone": "ZONE_A",
        },
    }
    assert validate_payload("vibration", "1.0", payload) is True


def test_validate_payload_unknown_sensor_type():
    # A sensor type with no schema should be allowed through
    payload = {"some_field": 5.5}
    assert validate_payload("nonexistent_sensor", "1.0", payload) is True
