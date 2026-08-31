import json
import time
import random
import datetime
import math
from pathlib import Path
import sys

# Ensure omniview is importable
sys.path.append(str(Path(__file__).resolve().parents[3]))

from omniview.edge.bots.stochastic import wanderer, sim_clock
import sys

# Ensure omniview is importable
sys.path.append(str(Path(__file__).resolve().parents[3]))

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
    return max(0.5, 1.0 + ((temp_c - 25.0) * 0.05))

def _read_edge_state() -> dict:
    state_file = Path(".edge_state.json")
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def _write_edge_state(payload: dict):
    state = _read_edge_state()
    state["ambient_temp_c"] = payload["data"].get("ambient_temp_c", 25.0)
    
    state_file = Path(".edge_state.json")
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Failed to write edge state: {e}")

# Ambient states are now fully driven by smooth sine waves and wanderer

def generate_reading() -> dict:
    global temp_wander, rh_wander
    wanderer.end_tick()
    now = datetime.datetime.fromtimestamp(sim_clock.now())
    time_in_hours = now.hour + (now.minute / 60.0)
    
    phase = (time_in_hours - 14.0) / 24.0 * 2 * math.pi
    base_temp = 40.0 + (math.cos(phase) * 10.0)
    base_rh = 40.0 - (math.cos(phase) * 15.0)
    
    # True stochastic wandering (smooth AR1)
    # Tightened so it hugs the sine wave without wandering off wildly
    temp_wander = wanderer.get("ambient_t", 0.1, 0.2)
    rh_wander = wanderer.get("ambient_rh", 0.1, 0.5)
    
    temp_c = base_temp + temp_wander
    rh_pct = max(0, min(100, base_rh + rh_wander))
    
    offset = compute_baseline_offset(temp_c)

    a = 17.27
    b = 237.7
    alpha = (a * temp_c) / (b + temp_c) + math.log(max(0.01, rh_pct) / 100.0)
    dew_point = round((b * alpha) / (a - alpha), 2)

    e = (rh_pct / 100.0) * 6.105 * math.exp((a * temp_c) / (b + temp_c))
    heat_index = round(temp_c + 0.33 * e - 0.70 * 0.5 - 4.0, 2)

    rssi = int(-65 - (temp_c - 25.0) * 0.3 + wanderer.get("rssi", 0.1, 1.5))

    # 5. Ugly Reality (Benign Glitch)
    # 0.1% chance of Modbus register corruption (stuck at 0)
    if random.random() < 0.001:
        rh_pct = 0.0

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
    
    _write_edge_state(payload)
    return payload

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Ambient Weather Bot... (Polling {POLL_INTERVAL}s interval)")
    print("Mode: True Stochastic Live Generation (Ornstein-Uhlenbeck + Shared State)")
    
    topic = build_topic("pune-isbm", "floor", "ambient")
    with OmniViewMQTTClient() as client:
        while True:
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            
            t = payload["data"]["ambient_temp_c"]
            h = payload["data"]["relative_humidity_pct"]
            print(f"[ambient_bot] Published -> Temp: {t}C | RH: {h}%")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
