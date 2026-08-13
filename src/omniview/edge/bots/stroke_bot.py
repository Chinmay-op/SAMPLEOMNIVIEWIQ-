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

DEVICE_ID = "Sick-IME-01"
POLL_INTERVAL = 15
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "stroke_schema.json"

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

current_counter = 1500000
operating_hours = 8000
NOMINAL_CYCLE_TIME_S = 22.0

def generate_reading(is_anomaly: bool = False) -> dict:
    global current_counter, operating_hours
    
    # At 22s/cycle, a 15s poll interval usually has 0 strokes, sometimes 1.
    # We will simulate this probabilistically: 15/22 ≈ 68% chance of 1 stroke, 32% chance of 0.
    if is_anomaly:
        strokes = random.choices([0, 1], weights=[0.8, 0.2])[0]
        cycle_time = round(random.uniform(25.5, 30.0), 2) if strokes > 0 else 0.0
        signal_quality = random.randint(180, 220) # degraded
    else:
        strokes = random.choices([0, 1], weights=[0.32, 0.68])[0]
        cycle_time = round(random.uniform(20.5, 24.5), 2) if strokes > 0 else 0.0
        signal_quality = random.randint(240, 255)
        
    current_counter += strokes
    operating_hours += (POLL_INTERVAL / 3600.0)
    
    # switching state true 20% of time (metal detected)
    bdc1 = random.random() < 0.20
    
    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "digital_pulse_counter",
        "data": {
            "switching_state_bdc1": bdc1,
            "counter_value": current_counter,
            "device_temperature_c": round(28.0 + random.uniform(0, 7.0), 1),
            "operating_hours": int(operating_hours),
            "signal_quality": signal_quality,
            "strokes_in_interval": strokes,
            "last_cycle_time_seconds": cycle_time
        }
    }
    return payload

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Stroke Pulse Counter Bot... (Polling {POLL_INTERVAL}s interval)")
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    topic = build_topic("pune-isbm", "isbm-01", "stroke")
    iterations = 0
    with OmniViewMQTTClient() as client:
        while True:
            is_anomaly = (iterations % 30 == 0) and iterations > 0
            payload = generate_reading(is_anomaly)
            validate_payload(payload)
            client.publish(topic, payload)
            print(f"[stroke_bot] Published to {topic} -> {json.dumps(payload)}")
            
            iterations += 1
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
