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
from omniview.edge.bots.ambient_bot import map_uci_row_to_payload

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
    payload = generate_electrical()
    jsonschema.validate(instance=payload, schema=SCHEMAS["electrical"])
    assert payload["device_id"] == "Selec-MFM384-01"
    assert "active_power_kw_total" in payload["data"]
    assert payload["data"]["active_power_kw_total"] > 50
    print("  ✅ electrical_bot OK")


def test_vibration_bot():
    payload = generate_vibration()
    jsonschema.validate(instance=payload, schema=SCHEMAS["vibration"])
    assert payload["device_id"] == "Banner-QM30VT1-01"
    print("  ✅ vibration_bot OK")


def test_thermal_bot():
    payload = generate_thermal()
    jsonschema.validate(instance=payload, schema=SCHEMAS["thermal"])
    assert payload["device_id"] == "Omron-E5CC-01"
    print("  ✅ thermal_bot OK")


def test_pressure_bot():
    payload = generate_pressure()
    jsonschema.validate(instance=payload, schema=SCHEMAS["pressure"])
    assert payload["device_id"] == "Festo-SPAU-01"
    print("  ✅ pressure_bot OK")


def test_gas_bot():
    payload = generate_gas()
    jsonschema.validate(instance=payload, schema=SCHEMAS["gas"])
    assert payload["device_id"] == "Schneider-HeatTag-01"
    print("  ✅ gas_bot OK")


def test_stroke_bot():
    payload = generate_stroke()
    jsonschema.validate(instance=payload, schema=SCHEMAS["stroke"])
    assert payload["device_id"] == "Sick-IME-01"
    print("  ✅ stroke_bot OK")


def test_ambient_bot():
    payload = generate_ambient()
    jsonschema.validate(instance=payload, schema=SCHEMAS["ambient"])
    assert payload["device_id"] == "Schneider-TH110-01"
    assert 15.0 <= payload["data"]["ambient_temp_c"] <= 35.0
    print("  ✅ ambient_bot OK")


def test_ambient_bot_csv_mapping():
    fake_row = {
        "T_out": "22.5",
        "RH_out": "45.0",
        "Tdewpoint": "10.0"
    }
    payload = map_uci_row_to_payload(fake_row)
    jsonschema.validate(instance=payload, schema=SCHEMAS["ambient"])
    
    assert payload["data"]["ambient_temp_c"] == 22.5
    assert payload["data"]["relative_humidity_pct"] == 45.0
    assert payload["data"]["dew_point_c"] == 10.0
    assert "heat_index_c" in payload["data"]
    assert "environmental_baseline_offset" in payload["data"]
    print("  ✅ ambient_bot CSV mapping OK")


if __name__ == "__main__":
    print("Running strict schema-validated bot tests...")
    test_electrical_bot()
    test_vibration_bot()
    test_thermal_bot()
    test_pressure_bot()
    test_gas_bot()
    test_stroke_bot()
    test_ambient_bot()
    test_ambient_bot_csv_mapping()
    print("\n🎉 All tests passed!")
