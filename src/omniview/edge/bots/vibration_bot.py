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

DEVICE_ID = "Banner-QM30VT1-01"
POLL_INTERVAL = 60
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "vibration_schema.json"

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

def classify_iso_zone(z_rms_velocity: float) -> str:
    if z_rms_velocity <= 2.8:   return "ZONE_A"
    elif z_rms_velocity <= 7.1: return "ZONE_B"
    elif z_rms_velocity <= 18.0: return "ZONE_C"
    else:                        return "ZONE_D"

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
bearing_wear_wander = 0.0
next_anomaly_time = 0.0
anomaly_active_until = 0.0

def get_poisson_bearing_defect():
    """Poisson timer for bearing degradation."""
    global next_anomaly_time, anomaly_active_until
    now = time.time()
    if now < anomaly_active_until:
        return True 
    if next_anomaly_time == 0.0:
        next_anomaly_time = now + random.expovariate(1.0 / 86400.0) # Mean: 24 hours
        return False
    if now >= next_anomaly_time:
        next_anomaly_time = now + random.expovariate(1.0 / 86400.0)
        anomaly_active_until = now + random.uniform(1800, 7200) # Lasts 30 mins to 2 hours
        return True
    return False

def generate_reading() -> dict:
    global bearing_wear_wander

    edge_state = _read_edge_state()
    machine_running = edge_state.get("machine_running", True)
    compressor_running = edge_state.get("compressor_running", 0) == 1
    ambient_temp = edge_state.get("ambient_temp_c", 25.0)
    
    is_bearing_defect = get_poisson_bearing_defect()

    if not machine_running:
        # Machine is off. Only tiny floor vibrations exist.
        z_rms = 0.2 + wanderer.get('vib_z_off', 0.1, 0.05)
        x_rms = 0.1 + wanderer.get('vib_x_off', 0.1, 0.02)
        z_peak = z_rms * 1.5
        x_peak = x_rms * 1.5
        hf_rms = z_rms * 0.1
        temp_c = ambient_temp
        z_kurtosis = 3.0 + wanderer.get('kurt_noise', 0.2, 0.1)
        x_kurtosis = 3.0 + wanderer.get('kurt_noise', 0.2, 0.1)
        peak_freq = 0.0
    else:
        # --- Live Mechanical Physics (AR1) ---
        theta_v = 0.02
        sigma_v = 0.15
        bearing_wear_wander = (1 - theta_v) * bearing_wear_wander + random.gauss(0, sigma_v)

        # Base running vibration
        base_rms = 1.5 + bearing_wear_wander
        
        # If the compressor kicks on, it adds massive shake to the chassis
        if compressor_running:
            base_rms += 2.5 + wanderer.get('comp_noise', 0.2, 0.5)

        if is_bearing_defect:
            # Defect state: Kurtosis spikes massively as a leading indicator, RMS increases moderately
            z_rms = base_rms + wanderer.get('z_defect', 0.1, 1.0) + 4.0
            z_peak = wanderer.get('z_peak_defect', 0.1, 2.0) + 11.5 # Spiky impacts
            hf_rms = wanderer.get('hf_defect', 0.1, 0.8) + 3.75
            temp_c = ambient_temp + 15.0 + wanderer.get('temp_defect', 0.05, 1.5) + 7.5 # Friction heat
            z_kurtosis = wanderer.get('z_peak_defect', 0.1, 2.0) + 11.5 # Massive Kurtosis spike
            peak_freq = 200.0 + wanderer.get('freq_defect', 0.1, 30.0) # High frequency defect
        else:
            # Normal healthy running
            z_rms = max(0.5, base_rms)
            z_peak = z_rms * 1.5 + wanderer.get('crest_noise', 0.2, 0.1)
            hf_rms = z_rms * 0.15
            temp_c = ambient_temp + 12.0 + wanderer.get('temp_noise', 0.1, 1.0)
            z_kurtosis = 3.0 + wanderer.get('kurt2', 0.1, 0.2) # Gaussian normal
            peak_freq = 37.5 + wanderer.get('freq_norm', 0.1, 5.0) # 1x-2x running speed

        x_rms = z_rms * 0.7 + wanderer.get('kurt_noise', 0.2, 0.1)
        x_peak = z_peak * 0.7 + wanderer.get('kurt_noise', 0.2, 0.1)
        x_kurtosis = z_kurtosis * 0.85 + wanderer.get('kurt_noise', 0.2, 0.1)

    zone = classify_iso_zone(z_rms)

    z_crest = round(z_peak / max(0.01, hf_rms), 2)
    x_crest = round(x_peak / max(0.01, x_rms * 0.05), 2)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "vibration_node",
        "data": {
            "z_axis_rms_velocity_mm_sec": round(z_rms, 2),
            "x_axis_rms_velocity_mm_sec": round(x_rms, 2),
            "z_axis_peak_acceleration_g": round(z_peak, 2),
            "x_axis_peak_acceleration_g": round(x_peak, 2),
            "high_frequency_rms_acceleration_g": round(hf_rms, 2),
            "z_axis_kurtosis": round(z_kurtosis, 2),
            "x_axis_kurtosis": round(x_kurtosis, 2),
            "z_axis_crest_factor": z_crest,
            "x_axis_crest_factor": x_crest,
            "peak_velocity_component_freq_hz": round(peak_freq, 1),
            "temperature_c": round(temp_c, 2),
            "iso_health_zone": zone,
            "data_source": "synthetic"
        }
    }
    return payload

from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Vibration Live Stochastic Bot... (Polling {POLL_INTERVAL}s interval)")
    print("Mode: True Stochastic Live Generation (Mechanical Physics + Shared State)")
    
    topic = build_topic("pune-isbm", "compressor-01", "vibration")
    with OmniViewMQTTClient() as client:
        while True:
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            
            z = payload["data"]["z_axis_rms_velocity_mm_sec"]
            k = payload["data"]["z_axis_kurtosis"]
            print(f"[vibration_bot] Published -> RMS: {z} mm/s | Kurtosis: {k}")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
