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

DEVICE_ID = "Festo-SPAU-01"
POLL_INTERVAL = 60
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "pressure_schema.json"

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


def raw_to_bar(raw_value: int) -> float:
    return round((raw_value / 16383.0) * 40.0, 2)

def bar_to_raw(pressure_bar: float) -> int:
    return int((pressure_bar / 40.0) * 16383)


current_pressure = 33.0

def generate_reading(is_anomaly: bool = False) -> dict:
    global current_pressure

    if is_anomaly:
        # Leak anomaly
        current_pressure = max(0.0, current_pressure - random.uniform(1.0, 3.0))
        pressure = current_pressure
        out1 = True # Low threshold
        out2 = pressure < 20.0 # Critical threshold
        status = 1
        comp_state = "LOADED"
        trend = "FALLING"
    else:
        # Normal
        current_pressure = round(random.uniform(28.0, 36.0), 2)
        pressure = current_pressure
        out1 = False
        out2 = False
        status = 0
        comp_state = random.choice(["LOADED", "UNLOADED"])
        trend = "STABLE"

    pdv_raw = bar_to_raw(pressure)
    temp_c = round(random.uniform(28.0, 40.0), 1)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "pressure_transmitter",
        "data": {
            "process_data_variable_raw": pdv_raw,
            "pressure_bar": pressure,
            "switching_output_1_active": out1,
            "switching_output_2_active": out2,
            "device_status_code": status,
            "internal_temperature_c": temp_c,
            "compressor_state": comp_state,
            "pressure_trend_5min": trend
        }
    }
    return payload

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Pressure Synthetic Data Bot... (Polling {POLL_INTERVAL}s interval)")
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    topic = build_topic("pune-isbm", "compressor-01", "pressure")
    iterations = 0
    with OmniViewMQTTClient() as client:
        while True:
            # Simulate sustained leak
            is_anomaly = (20 < iterations % 50 < 30)
            
            payload = generate_reading(is_anomaly)
            validate_payload(payload)
            client.publish(topic, payload)
            print(f"[pressure_bot] Published to {topic} -> {json.dumps(payload)}")
            
            iterations += 1
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
