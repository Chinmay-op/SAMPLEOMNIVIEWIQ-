"""
Tests for all 7 sensor bots (electrical, vibration, thermal, pressure, gas, stroke, ambient).
Verifies that each bot can generate a valid payload structure.
Strictly validates against the JSON schemas.

NOTE: After Vibhanshu's refactor, bots no longer accept `is_anomaly`.
Anomalies are now Poisson-triggered internally via stochastic timers.
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
from omniview.edge.bots.ambient_bot import map_uci_row_to_payload as map_uci_ambient
from omniview.edge.bots.gas_bot import map_uci_row_to_payload as map_uci_gas

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
    # Verify new datasheet-expanded fields are present
    assert "voltage_v_l1_n" in payload["data"]
    assert "delta_active_energy_kwh" in payload["data"]
    # Dev B: verify realistic power range
    assert payload["data"]["active_power_kw_total"] > 50
    print("  ✅ electrical_bot OK")


def test_vibration_bot():
    payload = generate_vibration()
    jsonschema.validate(instance=payload, schema=SCHEMAS["vibration"])
    assert payload["device_id"] == "Banner-QM30VT1-01"
    # Verify new datasheet-expanded fields
    assert "z_axis_kurtosis" in payload["data"]
    assert "data_source" in payload["data"]
    assert payload["data"]["iso_health_zone"] in ["ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D"]
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
    payload = map_uci_ambient(fake_row)
    jsonschema.validate(instance=payload, schema=SCHEMAS["ambient"])
    
    assert payload["data"]["ambient_temp_c"] == 22.5
    assert payload["data"]["relative_humidity_pct"] == 45.0
    assert payload["data"]["dew_point_c"] == 10.0
    assert "heat_index_c" in payload["data"]
    assert "environmental_baseline_offset" in payload["data"]
    print("  ✅ ambient_bot CSV mapping OK")


def test_gas_bot_csv_mapping():
    """Validate UCI AI4I 2020 row → gas schema payload mapping."""
    fake_row = {
        "Air temperature [K]": "298.15",      # → 25.0 °C panel temp
        "Process temperature [K]": "308.15",   # → 1.0 °C/min rate of rise
        "Torque [Nm]": "40.0",                 # → ~12.0 ppm gas
        "Tool wear [min]": "100",              # → ~4.0 particle index
        "Machine failure": "0",
        "HDF": "0"
    }
    payload = map_uci_gas(fake_row)
    jsonschema.validate(instance=payload, schema=SCHEMAS["gas"])

    # Verify temperature conversion (K → °C)
    assert payload["data"]["internal_panel_temp_c"] == 25.0
    # Verify rate of thermal rise (delta / 10)
    assert payload["data"]["rate_of_thermal_rise_c_per_min"] == 1.0
    # Verify gas concentration is in expected range (torque * 0.3 ≈ 12 ± wanderer)
    assert 10.0 <= payload["data"]["gas_concentration_ppm"] <= 15.0
    # Verify particle index is in expected range (wear * 0.04 ≈ 4 ± wanderer)
    assert 3.0 <= payload["data"]["micro_particle_index"] <= 6.0
    # Verify severity is NORMAL (no failure flags)
    assert payload["data"]["alert_severity_level"] == "NORMAL"
    # Verify derived fields are present
    assert "ambient_humidity_pct" in payload["data"]
    assert "air_quality_index" in payload["data"]
    assert 0 <= payload["data"]["air_quality_index"] <= 10
    print("  ✅ gas_bot CSV mapping OK")


def test_gas_bot_csv_mapping_failure():
    """Validate severity escalation when Machine failure + HDF flags are set."""
    critical_row = {
        "Air temperature [K]": "340.0",        # → 66.85 °C (hot!)
        "Process temperature [K]": "350.0",
        "Torque [Nm]": "70.0",                 # High stress
        "Tool wear [min]": "200",              # Worn tool
        "Machine failure": "1",
        "HDF": "1"
    }
    payload = map_uci_gas(critical_row)
    jsonschema.validate(instance=payload, schema=SCHEMAS["gas"])

    assert payload["data"]["alert_severity_level"] == "CRITICAL"
    assert payload["data"]["internal_panel_temp_c"] == 66.9  # 340 - 273.15
    print("  ✅ gas_bot CSV mapping (failure mode) OK")


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
    test_gas_bot_csv_mapping()
    test_gas_bot_csv_mapping_failure()
    print("\n🎉 All tests passed!")

