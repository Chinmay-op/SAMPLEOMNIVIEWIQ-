import json
import time
import random
import datetime
import math
from pathlib import Path
import sys
import argparse
import csv
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
    # Pune typical temperature: 21C to 29C
    base_temp = 25.0 + (math.cos(phase) * 4.0)
    base_rh = 40.0 - (math.cos(phase) * 15.0)
    
    # Weather perturbations to break the perfect sine wave:
    # 1. Cloud cover: randomly dims the heating (drops temp by 1-3C)
    cloud_cover = wanderer.get("cloud_cover", 0.02, 1.0)
    # 2. Wind gusts: short-lived cooling events
    wind_gust = wanderer.get("wind_gust", 0.05, 0.5)
    # 3. Slow day-to-day baseline drift (monsoon vs dry spell)
    # Reduced sigma from 1.5 to 0.2 so it stays within realistic seasonal bounds
    day_drift = wanderer.get("day_drift", 0.002, 0.2)
    # 4. Random sharp perturbation (rain event, door opening, etc.)
    rain_event = random.gauss(0, 0.3) if random.random() < 0.05 else 0.0
    
    # True stochastic wandering (smooth AR1)
    temp_wander = wanderer.get("ambient_t", 0.05, 0.5)
    rh_wander = wanderer.get("ambient_rh", 0.05, 1.0)
    
    temp_c = base_temp + cloud_cover + wind_gust + day_drift + rain_event + temp_wander
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
        "sensor_type": "ambient",
        "schema_version": "1.0",
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

def map_uci_row_to_payload(row: dict) -> dict:
    wanderer.end_tick()
    now = datetime.datetime.fromtimestamp(sim_clock.now())
    
    # Read from UCI columns
    try:
        temp_c = float(row.get("T_out", 25.0))
    except ValueError:
        temp_c = 25.0
        
    try:
        rh_pct = float(row.get("RH_out", 50.0))
    except ValueError:
        rh_pct = 50.0
        
    try:
        dew_point = float(row.get("Tdewpoint", 15.0))
    except ValueError:
        dew_point = 15.0

    offset = compute_baseline_offset(temp_c)

    # Compute heat index
    a = 17.27
    b = 237.7
    e = (rh_pct / 100.0) * 6.105 * math.exp((a * temp_c) / (b + temp_c))
    heat_index = round(temp_c + 0.33 * e - 0.70 * 0.5 - 4.0, 2)

    rssi = int(-65 - (temp_c - 25.0) * 0.3 + wanderer.get("rssi", 0.1, 1.5))

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": now.isoformat() + "Z",
        "sensor_type": "ambient",
        "schema_version": "1.0",
        "data": {
            "ambient_temp_c": round(temp_c, 2),
            "relative_humidity_pct": round(rh_pct, 1),
            "dew_point_c": round(dew_point, 2),
            "heat_index_c": heat_index,
            "wireless_signal_strength_dbm": rssi,
            "environmental_baseline_offset": round(offset, 2)
        }
    }
    
    _write_edge_state(payload)
    return payload

def read_csv_rows(csv_path: str):
    """Generator that infinitely loops over the CSV."""
    while True:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # Ensure required columns are present
            if not reader.fieldnames or not all(k in reader.fieldnames for k in ["T_out", "RH_out", "Tdewpoint"]):
                print(f"Error: CSV {csv_path} does not contain T_out, RH_out, Tdewpoint.")
                break
                
            for row in reader:
                yield row

def run_bot(csv_path=None):
    print(f"Starting Ambient Weather Bot... (Polling {POLL_INTERVAL}s interval)")
    
    csv_gen = None
    if csv_path:
        print(f"Mode: CSV Replay ({csv_path})")
        csv_gen = read_csv_rows(csv_path)
    else:
        print("Mode: True Stochastic Live Generation (Ornstein-Uhlenbeck + Shared State)")
    
    topic = build_topic("pune-isbm", "floor", "ambient")
    with OmniViewMQTTClient() as client:
        while True:
            if csv_gen:
                row = next(csv_gen)
                payload = map_uci_row_to_payload(row)
            else:
                payload = generate_reading()
                
            validate_payload(payload)
            client.publish(topic, payload)
            
            t = payload["data"]["ambient_temp_c"]
            h = payload["data"]["relative_humidity_pct"]
            print(f"[ambient_bot] Published -> Temp: {t}C | RH: {h}%")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ambient Weather Bot")
    parser.add_argument("--csv", type=str, help="Path to UCI appliances energy CSV for replay")
    args = parser.parse_args()
    run_bot(csv_path=args.csv)
