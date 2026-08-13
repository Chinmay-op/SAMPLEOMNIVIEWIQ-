"""
Tests for all 7 sensor bots (electrical, vibration, thermal, pressure, gas, stroke, ambient).
Verifies that each bot can generate a valid payload structure in both normal and anomaly modes.
Strictly validates against the JSON schemas.
"""

import sys
import json
import jsonschema
from pathlib import Path

# Add src to path so we can import bots directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniview.edge.bots import (
    generate_electrical,
    generate_vibration,
    generate_thermal,
    generate_pressure,
    generate_gas,
    generate_stroke,
    generate_ambient
)

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

def load_schema(name: str) -> dict:
    with open(SCHEMA_DIR / f"{name}_schema.json", "r") as f:
        return json.load(f)

# Load schemas once for tests
SCHEMAS = {
    "electrical": load_schema("electrical"),
    "vibration": load_schema("vibration"),
    "thermal": load_schema("thermal"),
    "pressure": load_schema("pressure"),
    "gas": load_schema("gas"),
    "stroke": load_schema("stroke"),
    "ambient": load_schema("ambient"),
}


def test_electrical_bot():
    # Normal
    payload = generate_electrical(is_anomaly=False)
    jsonschema.validate(instance=payload, schema=SCHEMAS["electrical"])
    assert payload["device_id"] == "Selec-MFM384-01"
    assert "active_power_kw_total" in payload["data"]

    # Anomaly
    payload = generate_electrical(is_anomaly=True)
    jsonschema.validate(instance=payload, schema=SCHEMAS["electrical"])
    assert payload["data"]["current_a_avg"] > 250.0
    print("  ✅ electrical_bot OK")


def test_vibration_bot():
    # Normal
    payload = generate_vibration(is_anomaly=False)
    jsonschema.validate(instance=payload, schema=SCHEMAS["vibration"])
    assert payload["device_id"] == "Banner-QM30VT1-01"
    assert payload["data"]["z_axis_rms_velocity_mm_sec"] <= 2.8

    # Anomaly
    payload = generate_vibration(is_anomaly=True)
    jsonschema.validate(instance=payload, schema=SCHEMAS["vibration"])
    assert payload["data"]["z_axis_rms_velocity_mm_sec"] > 7.1
    assert payload["data"]["iso_health_zone"] in ["ZONE_C", "ZONE_D"]
    print("  ✅ vibration_bot OK")


def test_thermal_bot():
    # Normal / Heating
    payload = generate_thermal(is_anomaly=False)
    jsonschema.validate(instance=payload, schema=SCHEMAS["thermal"])
    assert payload["device_id"] == "Omron-E5CC-01"
    
    # Anomaly
    payload = generate_thermal(is_anomaly=True)
    jsonschema.validate(instance=payload, schema=SCHEMAS["thermal"])
    assert payload["data"]["heater_burnout_alarm_hb"] is True
    print("  ✅ thermal_bot OK")


def test_pressure_bot():
    # Normal
    payload = generate_pressure(is_anomaly=False)
    jsonschema.validate(instance=payload, schema=SCHEMAS["pressure"])
    assert payload["device_id"] == "Festo-SPAU-01"
    
    # Anomaly
    payload = generate_pressure(is_anomaly=True)
    jsonschema.validate(instance=payload, schema=SCHEMAS["pressure"])
    # Anomaly simulates leak, so output 1 or 2 might be true eventually, 
    # but at least it shouldn't throw validation error
    print("  ✅ pressure_bot OK")


def test_gas_bot():
    # Normal
    payload = generate_gas(is_anomaly=False)
    jsonschema.validate(instance=payload, schema=SCHEMAS["gas"])
    assert payload["device_id"] == "Schneider-HeatTag-01"
    assert payload["data"]["alert_severity_level"] == "NORMAL"

    # Anomaly
    payload = generate_gas(is_anomaly=True)
    jsonschema.validate(instance=payload, schema=SCHEMAS["gas"])
    assert payload["data"]["alert_severity_level"] in ["WARNING", "ALARM", "CRITICAL"]
    print("  ✅ gas_bot OK")


def test_stroke_bot():
    # Normal
    payload = generate_stroke(is_anomaly=False)
    jsonschema.validate(instance=payload, schema=SCHEMAS["stroke"])
    assert payload["device_id"] == "Sick-IME-01"

    # Anomaly
    payload = generate_stroke(is_anomaly=True)
    jsonschema.validate(instance=payload, schema=SCHEMAS["stroke"])
    print("  ✅ stroke_bot OK")


def test_ambient_bot():
    # Ambient only has one mode
    payload = generate_ambient()
    jsonschema.validate(instance=payload, schema=SCHEMAS["ambient"])
    assert payload["device_id"] == "Schneider-TH110-01"
    assert 20.0 <= payload["data"]["ambient_temp_c"] <= 40.0
    print("  ✅ ambient_bot OK")


if __name__ == "__main__":
    print("Running strict schema-validated bot tests...")
    test_electrical_bot()
    test_vibration_bot()
    test_thermal_bot()
    test_pressure_bot()
    test_gas_bot()
    test_stroke_bot()
    test_ambient_bot()
    print("\n🎉 All 7 bots passed strict validation!")
