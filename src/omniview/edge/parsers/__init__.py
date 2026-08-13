"""
omniview.edge.parsers — Sensor Data Parsers
=============================================

Raw serial/CSV → structured JSON payloads, validated against DevB schemas.
"""

from omniview.edge.parsers.modbus_parser import parse_modbus_string
from omniview.edge.parsers.vibration_parser import parse_vibration_string
from omniview.edge.parsers.thermal_parser import parse_thermal_string
from omniview.edge.parsers.pressure_parser import parse_pressure_string
from omniview.edge.parsers.stroke_parser import parse_stroke_string
from omniview.edge.parsers.gas_parser import parse_gas_string
from omniview.edge.parsers.ambient_parser import parse_ambient_string

# Mapping: payload sensor_type (long) → topics.py sensor_type (short)
SENSOR_TYPE_TO_TOPIC = {
    "electrical_meter": "electrical",
    "vibration_node": "vibration",
    "thermal_probe": "thermal",
    "pressure_transmitter": "pressure",
    "digital_pulse_counter": "stroke",
    "gas_particle_sensor": "gas",
    "ambient_weather": "ambient",
}

__all__ = [
    "parse_modbus_string",
    "parse_vibration_string",
    "parse_thermal_string",
    "parse_pressure_string",
    "parse_stroke_string",
    "parse_gas_string",
    "parse_ambient_string",
    "SENSOR_TYPE_TO_TOPIC",
]
