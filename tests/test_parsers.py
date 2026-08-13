"""
Tests for all 7 sensor parsers.
Verifies that each parse function correctly converts a raw CSV string
into a valid JSON payload matching the expected schema structure.
"""

import json
import sys
from pathlib import Path

# Add src to path so we can import parsers directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniview.edge.parsers.modbus_parser import parse_modbus_string
from omniview.edge.parsers.vibration_parser import parse_vibration_string
from omniview.edge.parsers.thermal_parser import parse_thermal_string
from omniview.edge.parsers.pressure_parser import parse_pressure_string
from omniview.edge.parsers.stroke_parser import parse_stroke_string
from omniview.edge.parsers.gas_parser import parse_gas_string
from omniview.edge.parsers.ambient_parser import parse_ambient_string


def test_modbus_parser():
    raw = "Selec-MFM384-01,2026-07-15T10:00:00Z,240.5,416.3,370.0,245.0,265.0,100.0,0.924,50.02,150000.0,158000.0,265.5,53.1"
    result = parse_modbus_string(raw)
    assert result is not None, "modbus parser returned None"
    assert result["sensor_type"] == "electrical_meter"
    assert result["device_id"] == "Selec-MFM384-01"
    assert "voltage_v_ln_avg" in result["data"]
    assert "active_power_kw_total" in result["data"]
    print("  ✅ modbus_parser OK")


def test_vibration_parser():
    raw = "Banner-QM30VT1-01,2026-07-15T10:00:00Z,2.1,1.5,0.45,0.33,0.38,38.5,ZONE_A"
    result = parse_vibration_string(raw)
    assert result is not None, "vibration parser returned None"
    assert result["sensor_type"] == "vibration_node"
    assert "z_axis_rms_velocity_mm_sec" in result["data"]
    assert "iso_health_zone" in result["data"]
    print("  ✅ vibration_parser OK")


def test_thermal_parser():
    raw = "Omron-E5CC-01,2026-07-15T10:00:00Z,255.3,255.0,45.2,false,false,STABLE,AT_SETPOINT"
    result = parse_thermal_string(raw)
    assert result is not None, "thermal parser returned None"
    assert result["sensor_type"] == "thermal_probe"
    assert "present_value_pv_c" in result["data"]
    assert "set_point_sp_c" in result["data"]
    print("  ✅ thermal_parser OK")


def test_pressure_parser():
    raw = "Festo-SPAU-01,2026-07-15T10:00:00Z,13500,33.0,false,false,0,32.5,LOADED,STABLE"
    result = parse_pressure_string(raw)
    assert result is not None, "pressure parser returned None"
    assert result["sensor_type"] == "pressure_transmitter"
    assert "process_data_variable_raw" in result["data"]
    assert "pressure_bar" in result["data"]
    print("  ✅ pressure_parser OK")


def test_stroke_parser():
    raw = "Sick-IME-01,2026-07-15T10:00:00Z,true,1500050,31.2,8005,252,5,18.5"
    result = parse_stroke_string(raw)
    assert result is not None, "stroke parser returned None"
    assert result["sensor_type"] == "digital_pulse_counter"
    assert "counter_value" in result["data"]
    assert "switching_state_bdc1" in result["data"]
    print("  ✅ stroke_parser OK")


def test_gas_parser():
    raw = "Schneider-HeatTag-01,2026-07-15T10:00:00Z,1.25,3.50,35.2,0.05,NORMAL"
    result = parse_gas_string(raw)
    assert result is not None, "gas parser returned None"
    assert result["sensor_type"] == "gas_particle_sensor"
    assert "gas_concentration_ppm" in result["data"]
    assert "alert_severity_level" in result["data"]
    print("  ✅ gas_parser OK")


def test_ambient_parser():
    raw = "Schneider-TH110-01,2026-07-15T10:00:00Z,32.50,55.0,1.38"
    result = parse_ambient_string(raw)
    assert result is not None, "ambient parser returned None"
    assert result["sensor_type"] == "ambient_weather"
    assert "ambient_temp_c" in result["data"]
    assert "relative_humidity_pct" in result["data"]
    print("  ✅ ambient_parser OK")


if __name__ == "__main__":
    print("Running parser tests...")
    test_modbus_parser()
    test_vibration_parser()
    test_thermal_parser()
    test_pressure_parser()
    test_stroke_parser()
    test_gas_parser()
    test_ambient_parser()
    print("\n🎉 All 7 parser tests passed!")
