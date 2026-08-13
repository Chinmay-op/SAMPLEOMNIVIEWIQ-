"""
omniview.edge.bots — Synthetic Data Bots (Live Edge Simulators)
================================================================

Real-time sensor simulators that emit MQTT-like payloads for testing.
One bot per sensor family, 7 total.
"""

from omniview.edge.bots.electrical_bot import generate_reading as generate_electrical
from omniview.edge.bots.vibration_bot import generate_reading as generate_vibration
from omniview.edge.bots.thermal_bot import generate_reading as generate_thermal
from omniview.edge.bots.pressure_bot import generate_reading as generate_pressure
from omniview.edge.bots.gas_bot import generate_reading as generate_gas
from omniview.edge.bots.stroke_bot import generate_reading as generate_stroke
from omniview.edge.bots.ambient_bot import generate_reading as generate_ambient
