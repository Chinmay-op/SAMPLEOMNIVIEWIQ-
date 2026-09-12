import json
import time
import random
import datetime
from pathlib import Path
import sys
from omniview.edge.bots.stochastic import wanderer, sim_clock, PoissonTimer

sys.path.append(str(Path(__file__).resolve().parents[3]))

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
    # Is the machine actively producing strokes?
    strokes = payload["data"].get("strokes_in_interval", 0)
    state["machine_running"] = strokes > 0
    state["last_cycle_time"] = payload["data"].get("last_cycle_time_seconds", 0.0)
    
    state_file = Path(".edge_state.json")
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Failed to write edge state: {e}")


current_counter = 1500000
operating_hours = 8000

next_anomaly_time = 0.0
anomaly_active_until = 0.0

def get_poisson_anomaly():
    global next_anomaly_time, anomaly_active_until
    now = sim_clock.now()
    
    if now < anomaly_active_until:
        return True 
        
    if next_anomaly_time == 0.0:
        next_anomaly_time = now + random.expovariate(1.0 / 14400.0) # Mean: 4 hours
        return False
        
    if now >= next_anomaly_time:
        next_anomaly_time = now + random.expovariate(1.0 / 14400.0)
        anomaly_active_until = now + random.uniform(30, 180) # Jam lasts 30-180 seconds
        return True
        
    return False

def generate_reading() -> dict:
    global current_counter, operating_hours
    wanderer.end_tick()
    
    is_anomaly = get_poisson_anomaly()
    
    edge_state = _read_edge_state()
    line_pressure = edge_state.get("pneumatic_pressure", 38.0)
    
    # Rigid anchor: 15.0s per stroke. If pressure drops below 30 bar, cylinder loses force.
    if line_pressure < 30.0:
        base_cycle_time = 16.5
    else:
        base_cycle_time = 15.0
        
    # Mechanical variance (extremely tight Gaussian noise for rigid flat bands)
    # Real injection molders hold cycle time within +/- 0.03s
    cycle_noise = random.gauss(0, 0.015)
    actual_cycle_time = base_cycle_time + cycle_noise

    if is_anomaly:
        strokes = 0
        cycle_time = round(actual_cycle_time, 2)
        signal_quality = int(max(0, min(255, 255 - random.expovariate(1/50.0))))
    else:
        # At 15s/cycle, a 15s poll interval usually has 1 stroke
        strokes = 1 if random.random() < (15.0 / actual_cycle_time) else 0
        cycle_time = round(actual_cycle_time, 2)
        signal_quality = int(max(0, min(255, 253 + wanderer.get('sig_q', 0.2, 1.2))))
        
    current_counter += strokes
    operating_hours += (POLL_INTERVAL / 3600.0)

    # 5. Ugly Reality (Benign Glitch)
    # 0.1% chance of IO-Link comms timeout
    if random.random() < 0.001:
        cycle_time = 999.9

    bdc1 = (sim_clock.now() % actual_cycle_time) < (actual_cycle_time * 0.20) # True physical phase detection (20% of cycle)
    bdc2 = not bdc1
    sensing_margin = round((signal_quality / 255.0) * 100.0, 1)
    device_status = 0 if signal_quality > 180 else 1

    # AR1 process for chip temp based on ambient
    ambient = edge_state.get("ambient_temp_c", 25.0)
    chip_temp = round(ambient + 12.0 + wanderer.get('stroke_chip_temp', 0.1, 0.5), 1)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.fromtimestamp(sim_clock.now()).isoformat() + "Z",
        "sensor_type": "stroke",
        "schema_version": "1.0",
        "data": {
            "switching_state_bdc1": bdc1,
            "switching_state_bdc2": bdc2,
            "counter_value": current_counter,
            "device_temperature_c": chip_temp,
            "operating_hours": int(operating_hours),
            "signal_quality": signal_quality,
            "sensing_distance_margin_pct": sensing_margin,
            "device_status_code": device_status,
            "strokes_in_interval": strokes,
            "last_cycle_time_seconds": cycle_time
        }
    }
    
    _write_edge_state(payload)
    return payload

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Stroke Pulse Counter Bot... (Polling {POLL_INTERVAL}s interval)")
    print("Mode: True Stochastic Live Generation (AR1 + Poisson Jamming)")
    
    topic = build_topic("pune-isbm", "isbm-01", "stroke")
    with OmniViewMQTTClient() as client:
        while True:
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            
            c = payload["data"]["last_cycle_time_seconds"]
            s = payload["data"]["strokes_in_interval"]
            print(f"[stroke_bot] Published -> Strokes: {s} | Cycle Time: {c}s")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
