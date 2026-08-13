import json
import time
import random
import datetime
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

DEVICE_ID = "Schneider-HeatTag-01"
POLL_INTERVAL = 60
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "gas_schema.json"

try:
    with open(SCHEMA_PATH, 'r') as f:
        SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    SCHEMA = None

def validate_payload(payload):
    if SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error: {e.message}")


def compute_severity(gas_ppm: float, particle_idx: float) -> str:
    if gas_ppm > 80.0 or particle_idx > 100.0: return "CRITICAL"
    if gas_ppm > 30.0 or particle_idx > 50.0:  return "ALARM"
    if gas_ppm > 15.0 or particle_idx > 20.0:  return "WARNING"
    return "NORMAL"


def generate_reading(is_anomaly: bool = False) -> dict:
    if is_anomaly:
        # Simulate an ALARM or CRITICAL condition
        gas_ppm = round(random.uniform(35.0, 90.0), 2)
        micro_particles = round(random.uniform(60.0, 120.0), 2)
        internal_temp = round(35.0 + random.uniform(3.0, 7.0), 1)
        rate_of_rise = round(random.uniform(2.0, 5.0), 2)
    else:
        # Normal
        gas_ppm = round(random.uniform(0.0, 1.5), 2)
        micro_particles = round(random.uniform(0.0, 5.0), 2)
        internal_temp = round(random.uniform(30.0, 40.0), 1)
        rate_of_rise = round(random.uniform(-0.1, 0.1), 2)
        
    severity = compute_severity(gas_ppm, micro_particles)
        
    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "gas_particle_sensor",
        "data": {
            "gas_concentration_ppm": gas_ppm,
            "micro_particle_index": micro_particles,
            "internal_panel_temp_c": internal_temp,
            "rate_of_thermal_rise_c_per_min": rate_of_rise,
            "alert_severity_level": severity
        }
    }
    return payload

def run_bot():
    print(f"Starting Gas & Particle Sensor Bot... (Polling {POLL_INTERVAL}s interval)")
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    iterations = 0
    while True:
        is_anomaly = (iterations % 40 == 0) and iterations > 0
        payload = generate_reading(is_anomaly)
        validate_payload(payload)
        print(json.dumps(payload))
        
        iterations += 1
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
