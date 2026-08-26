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
    # Write compressor state for Electrical bot and Vibration bot
    comp_state = payload["data"].get("compressor_state", "OFF")
    state["compressor_running"] = 1 if comp_state == "LOADED" else 0
    state["pneumatic_pressure"] = payload["data"].get("pressure_bar", 33.0)
    
    state_file = Path(".edge_state.json")
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Failed to write edge state: {e}")

# Live State
current_pressure = 33.0
pressure_min_memory = 33.0
pressure_max_memory = 33.0
compressor_active = False

next_anomaly_time = 0.0
anomaly_active_until = 0.0

TEACH_SP1 = 25.0
TEACH_SP2 = 18.0

def get_poisson_anomaly():
    """Poisson timer for major pneumatic leaks."""
    global next_anomaly_time, anomaly_active_until
    now = sim_clock.now()
    if now < anomaly_active_until:
        return True 
    if next_anomaly_time == 0.0:
        next_anomaly_time = now + random.expovariate(1.0 / 43200.0) # Mean: 12 hours
        return False
    if now >= next_anomaly_time:
        next_anomaly_time = now + random.expovariate(1.0 / 43200.0)
        anomaly_active_until = now + random.uniform(300, 900) # Leak lasts 5-15 mins
        return True
    return False

def generate_reading() -> dict:
    global current_pressure, pressure_min_memory, pressure_max_memory, compressor_active
    wanderer.end_tick()

    edge_state = _read_edge_state()
    machine_running = edge_state.get("machine_running", True)
    ambient_temp = edge_state.get("ambient_temp_c", 25.0)
    voltage_sag = edge_state.get("grid_voltage_sag", False)

    is_leak = get_poisson_anomaly()

    # --- Live Pneumatic Physics ---
    dt = POLL_INTERVAL
    
    # Floors at zero: a pump can't pump backwards, a leak can't un-leak
    # θ tuned for 5-day runs: 0.05 gives realistic fluctuation without drift
    base_leak = max(0.0, 0.05 + wanderer.get("leak_base", 0.02, 0.005))
    base_pump = max(0.0, 0.2 + wanderer.get("pump_base", 0.05, 0.02))
    
    # Motor torque loss due to voltage sag
    if voltage_sag:
        base_pump *= 0.6  # 40% loss of pumping power

    if is_leak:
        leak_rate = base_leak * (current_pressure / 40.0) # Non-linear leak  # bar/sec loss
    elif machine_running:
        leak_rate = (base_leak * 0.2) * (current_pressure / 40.0)  # normal consumption rate
    else:
        leak_rate = (base_leak * 0.02) * (current_pressure / 40.0) # slow micro-leak when off

    # Compressor Control Logic (Hysteresis)
    if current_pressure < 28.0:
        compressor_active = True
    elif current_pressure > 36.0:
        compressor_active = False

    if compressor_active:
        pump_rate = base_pump * (1.0 - (current_pressure / 50.0)) # Non-linear compressor curve # bar/sec gain
    else:
        pump_rate = 0.0
        
    # Apply physics
    net_change = (pump_rate - leak_rate) * dt
    current_pressure += net_change
    current_pressure = max(0.0, min(current_pressure, 40.0)) # Clamp 0-40 bar

    # 5. Ugly Reality (Benign Glitch)
    # 0.1% chance of ADC momentary fault
    # Use a LOCAL variable so the persistent physics state is NOT corrupted
    reported_pressure = current_pressure
    if random.random() < 0.001:
        reported_pressure = 0.0

    # Trend calculation
    if net_change > 1.0:
        trend = "RISING"
    elif net_change < -1.0:
        trend = "FALLING"
    else:
        trend = "STABLE"

    if compressor_active:
        comp_state = "LOADED"
    elif machine_running:
        comp_state = "UNLOADED"
    else:
        comp_state = "OFF"

    # Switching outputs
    out1 = reported_pressure < TEACH_SP1
    out2 = reported_pressure < TEACH_SP2
    
    status = 3 if out2 else (1 if out1 else 0)

    pressure_min_memory = min(pressure_min_memory, current_pressure)
    pressure_max_memory = max(pressure_max_memory, current_pressure)

    pdv_raw = bar_to_raw(reported_pressure)
    
    # Internal chip temperature tracks ambient but is warmer
    chip_temp = round(ambient_temp + 5.0 + wanderer.get('pressure_chip_temp', 0.1, 0.2), 1)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.fromtimestamp(sim_clock.now()).isoformat() + "Z",
        "sensor_type": "pressure_transmitter",
        "data": {
            "process_data_variable_raw": pdv_raw,
            "pressure_bar": round(reported_pressure, 2),
            "pressure_unit": "bar",
            "pressure_min_memory_bar": round(pressure_min_memory, 2),
            "pressure_max_memory_bar": round(pressure_max_memory, 2),
            "teach_sp1_bar": TEACH_SP1,
            "teach_sp2_bar": TEACH_SP2,
            "switching_output_1_active": out1,
            "switching_output_2_active": out2,
            "device_status_code": status,
            "internal_temperature_c": chip_temp,
            "compressor_state": comp_state,
            "pressure_trend_5min": trend
        }
    }
    
    _write_edge_state(payload)
    return payload

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Pressure Live Stochastic Bot... (Polling {POLL_INTERVAL}s interval)")
    print("Mode: True Stochastic Live Generation (Pneumatic Physics + Shared State)")
    
    topic = build_topic("pune-isbm", "compressor-01", "pressure")
    with OmniViewMQTTClient() as client:
        while True:
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            
            p = payload["data"]["pressure_bar"]
            c = payload["data"]["compressor_state"]
            print(f"[pressure_bot] Published -> Pressure: {p}bar | Compressor: {c}")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
