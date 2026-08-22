import json
import time
import random
import datetime
from pathlib import Path
import sys
from omniview.edge.bots.stochastic import wanderer, PoissonTimer

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

def compute_severity(gas_ppm: float, particle_idx: float) -> str:
    if gas_ppm > 80.0 or particle_idx > 100.0: return "CRITICAL"
    if gas_ppm > 30.0 or particle_idx > 50.0:  return "ALARM"
    if gas_ppm > 15.0 or particle_idx > 20.0:  return "WARNING"
    return "NORMAL"

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
gas_wander = 0.0
particle_wander = 0.0
panel_temp = 35.0
smoldering_active = False

next_anomaly_time = 0.0
anomaly_active_until = 0.0

def get_poisson_smoldering():
    global next_anomaly_time, anomaly_active_until
    now = time.time()
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
    global gas_wander, particle_wander, panel_temp, smoldering_active

    edge_state = _read_edge_state()
    current_a = edge_state.get("current_a_avg", 100.0)
    ambient_temp = edge_state.get("ambient_temp_c", 25.0)

    # 1. Panel Temperature Physics (I^2R heating)
    # The electrical panel heats up based on the current flowing through it.
    ambient_cooling_rate = 0.001
    heat_coeff = 0.000005
    
    dt = POLL_INTERVAL
    heat_gained = (current_a ** 2) * heat_coeff * dt
    heat_lost = (panel_temp - ambient_temp) * ambient_cooling_rate * dt
    
    panel_temp += (heat_gained - heat_lost)
    
    # 2. Smoldering Logic (Wire insulation melting)
    is_anomaly = get_poisson_smoldering()
    
    if is_anomaly or panel_temp > 65.0:
        # If Poisson anomaly triggers, or if true physical temp exceeds 65C
        smoldering_active = True
    elif panel_temp < 40.0:
        smoldering_active = False

    # 3. Gas & Particle Generation (AR1)
    theta = 0.05
    gas_wander = (1 - theta) * gas_wander + random.gauss(0, 0.2)
    particle_wander = (1 - theta) * particle_wander + random.gauss(0, 0.5)

    if smoldering_active:
        # VOC gases and particles skyrocket as PVC melts
        gas_ppm = max(0.0, 30.0 + gas_wander * 5 + 15.0 + wanderer.get('gas_spike', 0.1, 5.0))
        micro_particles = max(0.0, 50.0 + particle_wander * 5 + 30.0 + wanderer.get('part_spike', 0.1, 10.0))
        rate_of_rise = round(3.0 + wanderer.get('rise_spike', 0.1, 1.0), 2)
    else:
        # Normal baseline offgassing
        gas_ppm = max(0.0, 1.0 + gas_wander)
        micro_particles = max(0.0, 3.0 + particle_wander)
        rate_of_rise = round(heat_gained - heat_lost, 2)

    severity = compute_severity(gas_ppm, micro_particles)

    if severity in ["ALARM", "CRITICAL"]:
        humidity = round(71.0 + wanderer.get('hum_h', 0.1, 5.0), 1)
    elif severity == "WARNING":
        humidity = round(57.5 + wanderer.get('hum_m', 0.1, 4.0), 1)
    else:
        humidity = round(46.5 + wanderer.get('hum_l', 0.1, 4.0), 1)

    aqi = min(10, int((gas_ppm / 10.0) + (micro_particles / 25.0)))

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "gas_particle_sensor",
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

def run_bot():
    print(f"Starting Gas Live Stochastic Bot... (Polling {POLL_INTERVAL}s interval)")
    print("Mode: True Stochastic Live Generation (I^2R Heating + VOC Offgassing)")
    
    topic = build_topic("pune-isbm", "compressor-01", "gas")
    with OmniViewMQTTClient() as client:
        while True:
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            
            g = payload["data"]["gas_concentration_ppm"]
            p = payload["data"]["micro_particle_index"]
            t = payload["data"]["internal_panel_temp_c"]
            print(f"[gas_bot] Published -> Panel Temp: {t}C | Gas: {g}ppm | Particles: {p}")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
