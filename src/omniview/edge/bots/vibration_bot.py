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

DEVICE_ID = "Banner-QM30VT1-01"
POLL_INTERVAL = 60
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "vibration_schema.json"

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


def classify_iso_zone(z_rms_velocity: float) -> str:
    if z_rms_velocity <= 2.8:   return "ZONE_A"
    elif z_rms_velocity <= 7.1: return "ZONE_B"
    elif z_rms_velocity <= 18.0: return "ZONE_C"
    else:                        return "ZONE_D"


def generate_reading(is_anomaly: bool = False) -> dict:
    if is_anomaly:
        z_rms = random.uniform(7.5, 18.5)
        x_rms = random.uniform(5.0, 12.0)
        z_peak = random.uniform(1.5, 3.0)
        x_peak = random.uniform(1.0, 2.5)
        hf_rms = random.uniform(1.5, 4.0)
        temp_c = random.uniform(38.0, 58.0) + 15.0
    else:
        z_rms = random.uniform(1.0, 2.8)
        x_rms = random.uniform(0.8, 2.0)
        z_peak = random.uniform(0.1, 0.5)
        x_peak = random.uniform(0.08, 0.4)
        hf_rms = random.uniform(0.1, 0.5)
        temp_c = random.uniform(38.0, 58.0)

    zone = classify_iso_zone(z_rms)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "vibration_node",
        "data": {
            "z_axis_rms_velocity_mm_sec": round(z_rms, 2),
            "x_axis_rms_velocity_mm_sec": round(x_rms, 2),
            "z_axis_peak_acceleration_g": round(z_peak, 2),
            "x_axis_peak_acceleration_g": round(x_peak, 2),
            "high_frequency_rms_acceleration_g": round(hf_rms, 2),
            "temperature_c": round(temp_c, 2),
            "iso_health_zone": zone
        }
    }
    return payload

def run_bot():
    print(f"Starting Vibration Synthetic Data Bot... (Polling {POLL_INTERVAL}s interval)")
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    iterations = 0
    while True:
        is_anomaly = (iterations % 30 == 0) and iterations > 0
        payload = generate_reading(is_anomaly)
        validate_payload(payload)
        print(json.dumps(payload))
        
        iterations += 1
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
