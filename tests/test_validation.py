import pytest
from omniview.ingest.validation import validate_payload


# ── Valid payload matching updated electrical_schema.json (Vibhanshu OI-54) ──
_VALID_ELECTRICAL = {
    "device_id": "Selec-MFM384-01",
    "timestamp": "2026-08-13T17:00:00Z",
    "sensor_type": "electrical_meter",
    "data": {
        "voltage_v_ll_avg": 414.8,
        "voltage_v_l1_n": 240.1,
        "voltage_v_l2_n": 239.2,
        "voltage_v_l3_n": 239.2,
        "current_a_avg": 205.3,
        "current_a_l1": 206.1,
        "current_a_l2": 204.5,
        "current_a_l3": 205.3,
        "current_a_neutral": 0.3,
        "active_power_kw_total": 140.2,
        "active_power_kw_l1": 46.8,
        "active_power_kw_l2": 46.7,
        "active_power_kw_l3": 46.7,
        "apparent_power_kva_total": 147.6,
        "reactive_power_kvar_total": 45.8,
        "power_factor_avg": 0.949,
        "power_factor_l1": 0.950,
        "power_factor_l2": 0.948,
        "power_factor_l3": 0.949,
        "frequency_hz": 50.02,
        "voltage_thd_percent": 2.5,
        "current_thd_percent": 11.2,
        "active_energy_kwh": 150042.5,
        "apparent_energy_kvah": 157544.6,
        "delta_active_energy_kwh": 0.58,
        "delta_apparent_energy_kvah": 0.61,
        "rolling_kva_15min": 148.1,
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
    # Vibration schema now requires expanded datasheet fields
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
            "z_axis_kurtosis": 3.1,
            "x_axis_kurtosis": 3.0,
            "z_axis_crest_factor": 3.5,
            "x_axis_crest_factor": 3.3,
            "peak_velocity_component_freq_hz": 25.0,
            "temperature_c": 42.5,
            "iso_health_zone": "ZONE_A",
            "data_source": "synthetic",
        },
    }
    assert validate_payload("vibration", "1.0", payload) is True


def test_validate_payload_unknown_sensor_type():
    # A sensor type with no schema should be allowed through
    payload = {"some_field": 5.5}
    assert validate_payload("nonexistent_sensor", "1.0", payload) is True
