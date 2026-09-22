import json
import time
import random
import datetime
import math
from pathlib import Path
import sys
import argparse
import csv
from omniview.edge.bots.stochastic import wanderer, sim_clock, PoissonTimer

sys.path.append(str(Path(__file__).resolve().parents[3]))

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



def _read_edge_state() -> dict:
    state_file = Path(".edge_state.json")
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

# Live State
current_gas = 1.2
current_particles = 3.0
panel_temp = 35.0
smoldering_active = False

next_anomaly_time = 0.0
anomaly_active_until = 0.0

def get_poisson_smoldering():
    global next_anomaly_time, anomaly_active_until
    now = sim_clock.now()
    if now < anomaly_active_until:
        return True 
    if next_anomaly_time == 0.0:
        next_anomaly_time = now + random.expovariate(1.0 / 172800.0) # Mean: 48 hours
        return False
    if now >= next_anomaly_time:
        next_anomaly_time = now + random.expovariate(1.0 / 172800.0)
        anomaly_active_until = now + random.uniform(600, 3600) # Lasts 10-60 mins
        return True
    return False

def generate_reading() -> dict:
    global current_gas, current_particles, panel_temp, smoldering_active
    wanderer.end_tick()

    edge_state = _read_edge_state()
    current_a = edge_state.get("current_a_avg", 100.0)
    ambient_temp = edge_state.get("ambient_temp_c", 25.0)
    thermal_pv = edge_state.get("thermal_pv", 25.0)

    # 1. Panel Temperature Physics (I^2R heating + Radiant Heat from Machine)
    # The electrical panel heats up based on the current flowing through it,
    # AND absorbs radiant heat from the massive nearby thermal machine.
    # Calibrated so ~305A (normal load) equilibrates ~38°C, well below 65°C threshold.
    # Only sustained overcurrent or Poisson-triggered smoldering pushes past 65°C.
    ambient_cooling_rate = 0.008
    heat_coeff = 0.000001
    radiant_coeff = 0.00005  # Calibrated: ~0.65°C/tick at 255°C — subtle coupling, not dominant
    
    dt = POLL_INTERVAL
    heat_gained = (current_a ** 2) * heat_coeff * dt
    heat_lost = (panel_temp - ambient_temp) * ambient_cooling_rate * dt
    radiant_gained = max(0.0, (thermal_pv - panel_temp) * radiant_coeff * dt)
    
    panel_temp += (heat_gained - heat_lost + radiant_gained)
    
    # 2. Smoldering Logic (Wire insulation melting)
    is_anomaly = get_poisson_smoldering()
    
    if is_anomaly or panel_temp > 65.0:
        # If Poisson anomaly triggers, or if true physical temp exceeds 65C
        smoldering_active = True
    elif panel_temp < 40.0:
        smoldering_active = False

    # 3. Gas & Particle Generation (Plume Decay)
    external_anomaly = edge_state.get("ambient_anomaly", False)
    
    if smoldering_active or external_anomaly:
        target_gas = 50.0
        target_part = 80.0
    else:
        target_gas = 1.2
        target_part = 3.0

    # Exponential plume dynamics (fast fill, slow ventilation decay)
    if current_gas < target_gas:
        current_gas += (target_gas - current_gas) * 0.2
        current_particles += (target_part - current_particles) * 0.2
    else:
        current_gas -= (current_gas - target_gas) * 0.05
        current_particles -= (current_particles - target_part) * 0.05

    # Add gentle organic "plumps" around the baseline
    gas_ppm = max(0.0, current_gas + wanderer.get('gas_plump', 0.05, 0.15))
    micro_particles = max(0.0, current_particles + wanderer.get('part_plump', 0.1, 0.5))
    
    rate_of_rise = round(heat_gained - heat_lost, 2)


    # 5. Ugly Reality (Benign Glitch) — MUST happen before derived fields
    # Disabled the 1000 PPM glitch because it completely destroys graph scaling (zooms Y-axis out too far).
    # if random.random() < 0.001:
    #     gas_ppm = 1000.0
    if random.random() < 0.001:
        micro_particles = 1000.0

    # Severity derived from internal physical state, not visible sensor columns
    # (prevents target leakage — model must learn physics, not thresholds)
    if smoldering_active and panel_temp > 65.0:
        severity = "CRITICAL"
    elif smoldering_active:
        severity = "ALARM"
    elif panel_temp > 50.0:
        severity = "WARNING"
    else:
        severity = "NORMAL"

    # Humidity is an independent environmental variable, NOT derived from severity
    humidity = round(50.0 + wanderer.get('humidity', 0.05, 2.0), 1)
    humidity = max(20.0, min(95.0, humidity))  # Clamp to physical range

    aqi = min(10, int((gas_ppm / 10.0) + (micro_particles / 25.0)))

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.fromtimestamp(sim_clock.now()).isoformat() + "Z",
        "sensor_type": "gas",
        "schema_version": "1.0",
        "data": {
            "gas_concentration_ppm": round(gas_ppm, 2),
            "micro_particle_index": round(micro_particles, 2),
            "internal_panel_temp_c": round(panel_temp, 1),
            "rate_of_thermal_rise_c_per_min": rate_of_rise,
            "ambient_humidity_pct": humidity,
            "air_quality_index": aqi,
            "alert_severity_level": severity
        }
    }
    return payload

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def map_uci_row_to_payload(row: dict) -> dict:
    """Map a UCI AI4I 2020 Predictive Maintenance CSV row to a gas schema payload.

    Column mapping (AI4I 2020 → gas schema):
      - Air temperature [K]     → internal_panel_temp_c (K → °C)
      - Process temperature [K] → rate_of_thermal_rise_c_per_min (delta / 10)
      - Torque [Nm]             → gas_concentration_ppm (proxy: stress → outgassing)
      - Tool wear [min]         → micro_particle_index (proxy: degradation → particles)
      - Machine failure + HDF   → alert_severity_level
    """
    wanderer.end_tick()
    now = datetime.datetime.fromtimestamp(sim_clock.now())

    # Air temperature [K] → panel temp in °C
    try:
        air_temp_k = float(row.get("Air temperature [K]", 298.15))
    except (ValueError, TypeError):
        air_temp_k = 298.15
    panel_temp_c = round(air_temp_k - 273.15, 1)

    # Process temperature [K] → rate of thermal rise (delta between process and air, scaled)
    try:
        process_temp_k = float(row.get("Process temperature [K]", 308.15))
    except (ValueError, TypeError):
        process_temp_k = 308.15
    rate_of_rise = round((process_temp_k - air_temp_k) / 10.0, 2)

    # Torque [Nm] → gas concentration proxy (higher torque = more mechanical stress = outgassing)
    # Typical torque range: 3–77 Nm. Scale: torque * 0.3 → ~0.9–23 ppm
    try:
        torque = float(row.get("Torque [Nm]", 40.0))
    except (ValueError, TypeError):
        torque = 40.0
    gas_ppm = round(max(0.0, torque * 0.3 + wanderer.get('gas_uci', 0.05, 0.15)), 2)

    # Tool wear [min] → micro particle index (degradation produces particles)
    # Typical range: 0–253 min. Scale: wear * 0.04 → 0–10 index
    try:
        tool_wear = float(row.get("Tool wear [min]", 0.0))
    except (ValueError, TypeError):
        tool_wear = 0.0
    micro_particles = round(max(0.0, tool_wear * 0.04 + wanderer.get('part_uci', 0.1, 0.3)), 2)

    # Humidity from wanderer (independent environmental variable)
    humidity = round(50.0 + wanderer.get('humidity', 0.05, 2.0), 1)
    humidity = max(20.0, min(95.0, humidity))

    # Air quality index (same formula as stochastic bot)
    aqi = min(10, int((gas_ppm / 10.0) + (micro_particles / 25.0)))

    # Severity from Machine failure + HDF (Heat Dissipation Failure) flags
    try:
        machine_failure = int(row.get("Machine failure", 0))
    except (ValueError, TypeError):
        machine_failure = 0
    try:
        hdf = int(row.get("HDF", 0))
    except (ValueError, TypeError):
        hdf = 0

    if machine_failure == 1 and hdf == 1:
        severity = "CRITICAL"
    elif machine_failure == 1:
        severity = "ALARM"
    elif panel_temp_c > 50.0:
        severity = "WARNING"
    else:
        severity = "NORMAL"

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": now.isoformat() + "Z",
        "sensor_type": "gas",
        "schema_version": "1.0",
        "data": {
            "gas_concentration_ppm": gas_ppm,
            "micro_particle_index": micro_particles,
            "internal_panel_temp_c": panel_temp_c,
            "rate_of_thermal_rise_c_per_min": rate_of_rise,
            "ambient_humidity_pct": humidity,
            "air_quality_index": aqi,
            "alert_severity_level": severity
        }
    }
    return payload

def read_csv_rows(csv_path: str):
    """Generator that infinitely loops over the CSV."""
    while True:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # Ensure required columns are present
            required = ["Air temperature [K]", "Process temperature [K]", "Torque [Nm]", "Tool wear [min]"]
            if not reader.fieldnames or not all(k in reader.fieldnames for k in required):
                print(f"Error: CSV {csv_path} does not contain required columns: {required}")
                break

            for row in reader:
                yield row

def run_bot(csv_path=None):
    print(f"Starting Gas Bot... (Polling {POLL_INTERVAL}s interval)")

    csv_gen = None
    if csv_path:
        print(f"Mode: CSV Replay ({csv_path})")
        csv_gen = read_csv_rows(csv_path)
    else:
        print("Mode: True Stochastic Live Generation (I^2R Heating + VOC Offgassing)")

    topic = build_topic("pune-isbm", "compressor-01", "gas")
    with OmniViewMQTTClient() as client:
        while True:
            if csv_gen:
                row = next(csv_gen)
                payload = map_uci_row_to_payload(row)
            else:
                payload = generate_reading()

            validate_payload(payload)
            client.publish(topic, payload)

            g = payload["data"]["gas_concentration_ppm"]
            p = payload["data"]["micro_particle_index"]
            t = payload["data"]["internal_panel_temp_c"]
            print(f"[gas_bot] Published -> Panel Temp: {t}C | Gas: {g}ppm | Particles: {p}")

            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gas / Particle Overheating Bot")
    parser.add_argument("--csv", type=str, help="Path to UCI AI4I 2020 CSV for replay")
    args = parser.parse_args()
    run_bot(csv_path=args.csv)
