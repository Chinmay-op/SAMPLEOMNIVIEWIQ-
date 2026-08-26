import os
import json
import time
import random
import datetime
import csv
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

import sys
from omniview.edge.bots.stochastic import wanderer, sim_clock, PoissonTimer
sys.path.append(str(Path(__file__).resolve().parents[3]))
from omniview.config import CALIBRATION_CURRENT_OFFSET_A, CALIBRATION_VOLTAGE_OFFSET_V

DEVICE_ID = "Selec-MFM384-01"
POLL_INTERVAL = 15
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "electrical_schema.json"

try:
    with open(SCHEMA_PATH, 'r') as f:
        ELECTRICAL_SCHEMA = json.load(f)
except Exception:
    ELECTRICAL_SCHEMA = None

def validate_payload(payload):
    if ELECTRICAL_SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=ELECTRICAL_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error: {e.message}")

# --- Live Stochastic State ---
cumulative_kwh = 150000.0
cumulative_kvah = 157500.0  # Tracks apparent energy independently from active energy
# Ornstein-Uhlenbeck (AR1) states for organic wandering
current_voltage_wander = 0.0  
current_load_wander = 0.0

# Poisson Anomaly Timer
next_anomaly_time = 0.0
anomaly_active_until = 0.0

def _read_edge_state() -> dict:
    state_file = Path(".edge_state.json")
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def _write_edge_state(payload: dict, is_anomaly: bool):
    state = _read_edge_state()
    state["machine_running"] = True
    state["current_a_avg"] = payload["data"].get("current_a_avg", 120.0)
    state["grid_voltage_sag"] = is_anomaly
    
    state_file = Path(".edge_state.json")
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Failed to write edge state: {e}")

def get_poisson_anomaly():
    """Uses a Poisson process to trigger anomalies randomly, not repetitively."""
    global next_anomaly_time, anomaly_active_until
    now = sim_clock.now()
    
    if now < anomaly_active_until:
        return True
        
    if next_anomaly_time == 0.0:
        # Initialize first anomaly (mean time: 2 hours)
        next_anomaly_time = now + random.expovariate(1.0 / 7200.0)
        return False
        
    if now >= next_anomaly_time:
        # Trigger anomaly, and schedule the next one
        next_anomaly_time = now + random.expovariate(1.0 / 7200.0)
        anomaly_active_until = now + random.uniform(60, 300) # Lasts 1-5 mins
        return True
        
    return False

def generate_reading() -> dict:
    wanderer.end_tick()
    """Generates correlated readings using live stochastic AR(1) math."""
    global cumulative_kwh, cumulative_kvah, current_voltage_wander, current_load_wander
    
    # 1. Read downstream dependencies
    edge_state = _read_edge_state()
    # E.g., if a pneumatic compressor is running, it draws 40A.
    # If the thermal heater is running at 100% duty, it draws 25A (UNLESS heater is burnt out).
    compressor_load = edge_state.get("compressor_running", 0) * 40.0
    
    if edge_state.get("heater_failed", False):
        thermal_load = 0.0  # Zero electrical draw if heater element is burnt out
    else:
        thermal_load = edge_state.get("thermal_duty_cycle", 0.0) * 25.0
    
    # Base physics loads (if upstream bots aren't running, assume defaults)
    base_machine_load = 120.0 + compressor_load + thermal_load
    
    # 2. Apply Ornstein-Uhlenbeck (AR1) Process for true organic wandering
    # x[t] = (1 - theta) * x[t-1] + theta * mean + sigma * noise
    theta_v = 0.1 # Mean reversion speed for voltage
    sigma_v = 0.5 # Volatility for voltage
    current_voltage_wander = (1 - theta_v) * current_voltage_wander + random.gauss(0, sigma_v)
    
    theta_l = 0.05 # Mean reversion speed for load
    sigma_l = 1.2  # Volatility for load
    current_load_wander = (1 - theta_l) * current_load_wander + random.gauss(0, sigma_l)
    
    # 3. Check for Poisson Anomaly BEFORE computing derived values
    # (ensures voltage sag and current/PF spike land in the same row)
    is_anomaly = get_poisson_anomaly()
    anomaly_voltage_drop = 0.0
    anomaly_current_spike = 0.0
    anomaly_pf_crash = 0.0
    if is_anomaly:
        print("[!] Poisson Anomaly Triggered! (Grid Voltage Sag)")
        anomaly_voltage_drop = random.uniform(40.0, 80.0)  # Voltage Sag
        anomaly_current_spike = random.uniform(80.0, 150.0)   # Massive current spike
        anomaly_pf_crash = 0.15                                # Power factor crashes

    # 4. Calculate actual values (now incorporating any anomaly effects)
    voltage_ll = max(0.0, 415.0 + current_voltage_wander + CALIBRATION_VOLTAGE_OFFSET_V - anomaly_voltage_drop)
    current_avg = max(0.0, base_machine_load + current_load_wander + CALIBRATION_CURRENT_OFFSET_A + anomaly_current_spike)
    pf_avg = 0.95 + wanderer.get('pf', 0.1, 0.005) - anomaly_pf_crash

    v_ln_avg = voltage_ll / 1.732

    # --- Per-phase voltages (slight imbalance) ---
    v_l1 = v_ln_avg * (1.0 + wanderer.get('v_phase_l1', 0.1, 0.005))
    v_l2 = v_ln_avg * (1.0 + wanderer.get('v_phase_l2', 0.1, 0.005))
    v_l3 = 3.0 * v_ln_avg - v_l1 - v_l2

    # --- Per-phase currents (load imbalance) ---
    i_l1 = current_avg * (1.0 + wanderer.get('i_phase_l1', 0.1, 0.02))
    i_l2 = current_avg * (1.0 + wanderer.get('i_phase_l2', 0.1, 0.02))
    i_l3 = 3.0 * current_avg - i_l1 - i_l2
    i_neutral = abs(i_l1 - i_l2) * random.uniform(0.10, 0.25)

    # --- Power calculations ---
    kw = (voltage_ll * current_avg * pf_avg * 1.732) / 1000
    kva = (voltage_ll * current_avg * 1.732) / 1000
    kvar = (kva**2 - kw**2)**0.5 if kva > kw else 0.0

    # Per-phase active power
    kw_l1 = (kw / 3.0) * (1.0 + wanderer.get('kw_phase_l1', 0.1, 0.01))
    kw_l2 = (kw / 3.0) * (1.0 + wanderer.get('kw_phase_l2', 0.1, 0.01))
    kw_l3 = kw - kw_l1 - kw_l2

    # --- THD (Total Harmonic Distortion) ---
    load_ratio = min(1.0, kw / 200.0)
    thd_v = round(2.0 + load_ratio * 3.0 + wanderer.get('thd_v', 0.1, 0.2), 2)
    thd_i = round(5.0 + load_ratio * 10.0 + wanderer.get('thd_i', 0.1, 0.4), 2)

    rolling_kva = kva + wanderer.get('kva', 0.1, 2.0)

    delta_kwh = kw * (POLL_INTERVAL / 3600.0)
    delta_kvah = kva * (POLL_INTERVAL / 3600.0)
    cumulative_kwh += delta_kwh
    cumulative_kvah += delta_kvah

    # 5. Ugly Reality (Quantization & Missing Data)
    # 0.1% chance of a dropped packet (frozen buffer simulation)
    # Use a LOCAL variable so it doesn't create internally inconsistent rows
    reported_current = current_avg
    if random.random() < 0.001:
        reported_current = 0.0

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.fromtimestamp(sim_clock.now()).isoformat() + "Z",
        "sensor_type": "electrical_meter",
        "data": {
            "voltage_v_ll_avg": round(voltage_ll, 2),
            "voltage_v_l1_n": round(v_l1, 2),
            "voltage_v_l2_n": round(v_l2, 2),
            "voltage_v_l3_n": round(v_l3, 2),
            "current_a_avg": round(reported_current, 2),
            "current_a_l1": round(i_l1, 2),
            "current_a_l2": round(i_l2, 2),
            "current_a_l3": round(i_l3, 2),
            "current_a_neutral": round(i_neutral, 2),
            "active_power_kw_total": round(kw, 2),
            "active_power_kw_l1": round(kw_l1, 2),
            "active_power_kw_l2": round(kw_l2, 2),
            "active_power_kw_l3": round(kw_l3, 2),
            "apparent_power_kva_total": round(kva, 2),
            "reactive_power_kvar_total": round(kvar, 2),
            "power_factor_avg": round(pf_avg, 3),
            "power_factor_l1": round(pf_avg + wanderer.get('pf_l1', 0.1, 0.003), 3),
            "power_factor_l2": round(pf_avg + wanderer.get('pf_l2', 0.1, 0.003), 3),
            "power_factor_l3": round(pf_avg + wanderer.get('pf_l3', 0.1, 0.003), 3),
            "frequency_hz": round(50.0 + wanderer.get('freq', 0.05, 0.02), 2),
            "voltage_thd_percent": thd_v,
            "current_thd_percent": thd_i,
            "active_energy_kwh": round(cumulative_kwh, 2),
            "apparent_energy_kvah": round(cumulative_kvah, 2),
            "delta_active_energy_kwh": round(delta_kwh, 4),
            "delta_apparent_energy_kvah": round(delta_kvah, 4),
            "rolling_kva_15min": round(rolling_kva, 2)
        }
    }
    
    _write_edge_state(payload, is_anomaly)
    return payload

def cast_or_default(value, cast_type, default=0.0):
    try:
        return cast_type(value)
    except (ValueError, TypeError):
        return default

def map_csv_row_to_payload(row):
    """Fallback for CSV replay if needed."""
    voltage_ll = cast_or_default(row.get("voltage_v_ll_avg", 415.0), float)
    current = cast_or_default(row.get("current_a_avg", 200.0), float)
    pf = cast_or_default(row.get("power_factor_avg", 0.95), float)
    kw = cast_or_default(row.get("active_power_kw_total"), float, default=(voltage_ll * current * pf * 1.732) / 1000)
    kva = cast_or_default(row.get("apparent_power_kva_total"), float, default=(voltage_ll * current * 1.732) / 1000)
    kvar = (kva**2 - kw**2)**0.5 if kva > kw else 0.0

    payload = {
        "device_id": row.get("device_id", DEVICE_ID),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "electrical_meter",
        "data": {
            "voltage_v_ln_avg": round(voltage_ll / 1.732, 2),
            "voltage_v_ll_avg": round(voltage_ll, 2),
            "current_a_avg": round(current, 2),
            "active_power_kw_total": round(kw, 2),
            "apparent_power_kva_total": round(kva, 2),
            "reactive_power_kvar_total": round(kvar, 2),
            "power_factor_avg": round(pf, 3),
            "frequency_hz": cast_or_default(row.get("frequency_hz", 50.0), float),
            "active_energy_kwh": cast_or_default(row.get("active_energy_kwh", 150000.0), float),
            "apparent_energy_kvah": cast_or_default(row.get("apparent_energy_kvah", 158000.0), float),
            "rolling_kva_15min": cast_or_default(row.get("rolling_kva_15min", 85.0), float),
            "md_proximity_percent": cast_or_default(row.get("md_proximity_percent", 50.0), float)
        }
    }
    
    _write_edge_state(payload)
    return payload


from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    csv_path = os.environ.get("ELECTRICAL_CSV_PATH", "data/AV11.csv")
    csv_file = Path(csv_path)

    print(f"Starting Electrical Publisher... (Polling {POLL_INTERVAL}s interval)")
    print("Mode: True Stochastic Live Generation (Ornstein-Uhlenbeck + Poisson)")
    
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    topic = build_topic("pune-isbm", "compressor-01", "electrical")
    
    with OmniViewMQTTClient() as client:
        while True:
            # We strictly generate live stochastic data now
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            
            # Print a condensed preview to the console for the manager to see
            v = payload["data"]["voltage_v_ll_avg"]
            a = payload["data"]["current_a_avg"]
            kw = payload["data"]["active_power_kw_total"]
            print(f"[electrical_bot] Published -> V: {v}V | I: {a}A | P: {kw}kW")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
