import json
import time
import random
import datetime
import math
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

DEVICE_ID = "Schneider-TH110-01"
POLL_INTERVAL = 60
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "ambient_schema.json"

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


def compute_baseline_offset(temp_c: float) -> float:
    """Normalizes around 25°C. Above 25°C, chiller works harder."""
    return max(0.5, 1.0 + ((temp_c - 25.0) * 0.05))


def generate_reading() -> dict:
    # Ambient doesn't have an 'anomaly' mode, it's just environmental.
    now = datetime.datetime.utcnow()
    time_in_hours = now.hour + (now.minute / 60.0)
    
    # Pune climate: Peak at 14:00, lowest at 05:00
    phase = (time_in_hours - 14.0) / 24.0 * 2 * math.pi
    temp_c = 30.0 + (math.cos(phase) * 8.0) + random.uniform(-0.5, 0.5)
    rh_pct = 60.0 - (math.cos(phase) * 20.0) + random.uniform(-2.0, 2.0)
    
    offset = compute_baseline_offset(temp_c)

    # --- Dew point: Magnus formula ---
    a = 17.27
    b = 237.7
    alpha = (a * temp_c) / (b + temp_c) + math.log(max(0.01, rh_pct) / 100.0)
    dew_point = round((b * alpha) / (a - alpha), 2)

    # --- Heat index: simplified Steadman formula ---
    e = (rh_pct / 100.0) * 6.105 * math.exp((a * temp_c) / (b + temp_c))
    heat_index = round(temp_c + 0.33 * e - 0.70 * 0.5 - 4.0, 2)

    # --- Wireless RSSI: degrades with temperature (more EMI from hot equipment) ---
    rssi = int(-65 - (temp_c - 25.0) * 0.3 + random.uniform(-3, 3))

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": now.isoformat() + "Z",
        "sensor_type": "ambient_weather",
        "data": {
            "ambient_temp_c": round(temp_c, 2),
            "relative_humidity_pct": round(rh_pct, 1),
            "dew_point_c": dew_point,
            "heat_index_c": heat_index,
            "wireless_signal_strength_dbm": rssi,
            "environmental_baseline_offset": round(offset, 2)
        }
    }
    return payload


from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Ambient Weather Bot... (Polling {POLL_INTERVAL}s interval)")
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    topic = build_topic("pune-isbm", "floor", "ambient")
    with OmniViewMQTTClient() as client:
        while True:
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            print(f"[ambient_bot] Published to {topic} -> {json.dumps(payload)}")
            
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_bot()
