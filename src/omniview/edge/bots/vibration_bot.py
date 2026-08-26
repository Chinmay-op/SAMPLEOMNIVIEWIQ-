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
defect_severity = 0.0  # Ramps 0→1 gradually during bearing defect
next_anomaly_time = 0.0
anomaly_active_until = 0.0

def get_poisson_bearing_defect():
    """Poisson timer for bearing degradation."""
    global next_anomaly_time, anomaly_active_until
    now = sim_clock.now()
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
    global bearing_wear_wander, defect_severity
    wanderer.end_tick()

    edge_state = _read_edge_state()
    machine_running = edge_state.get("machine_running", True)
    compressor_running = edge_state.get("compressor_running", 0) == 1
    ambient_temp = edge_state.get("ambient_temp_c", 25.0)
    voltage_sag = edge_state.get("grid_voltage_sag", False)
    
    is_bearing_defect = get_poisson_bearing_defect()

    if not machine_running:
        # Machine is off. Only tiny floor vibrations exist.
        # Clamp at zero — RMS is a squared-root quantity, physically cannot be negative
        z_rms = max(0.0, 0.2 + wanderer.get('vib_z_off', 0.1, 0.05))
        x_rms = max(0.0, 0.1 + wanderer.get('vib_x_off', 0.1, 0.02))
        z_peak = z_rms * 1.5
        x_peak = x_rms * 1.5
        hf_rms = z_rms * 0.1
        temp_c = ambient_temp
        z_kurtosis = 3.0 + wanderer.get('kurt_z_off', 0.2, 0.1)
        x_kurtosis = 3.0 + wanderer.get('kurt_x_off', 0.2, 0.1)
        peak_freq = 0.0
    else:
        # --- Live Mechanical Physics (AR1) ---
        theta_v = 0.02
        sigma_v = 0.15
        bearing_wear_wander = (1 - theta_v) * bearing_wear_wander + random.gauss(0, sigma_v)

        # Base running vibration (floored — RMS cannot go negative)
        base_rms = max(0.3, 1.5 + bearing_wear_wander)
        
        # If the compressor kicks on, it adds massive shake to the chassis
        if compressor_running:
            base_rms += 2.5 + wanderer.get('comp_noise', 0.2, 0.5)
            
        # Motor slip caused by electrical voltage sag
        if voltage_sag:
            base_rms += 1.2  # Unbalanced magnetic pull increases vibration

        if is_bearing_defect:
            # Gradual ramp: takes ~30 ticks (30 min at 60s) to reach full severity
            defect_severity = min(1.0, defect_severity + 0.03)
        else:
            # Faster recovery when defect clears
            defect_severity = max(0.0, defect_severity - 0.05)

        if defect_severity > 0.0:
            # Kurtosis leads RMS — reaches full severity 1.5× faster (real bearing physics)
            kurt_severity = min(1.0, defect_severity * 1.5)
            # Defect state: features scale with severity rather than jumping instantly
            z_rms = max(0.0, base_rms + (wanderer.get('z_defect', 0.1, 1.0) + 4.0) * defect_severity)
            z_peak = max(0.0, (wanderer.get('z_peak_defect', 0.1, 2.0) + 11.5) * defect_severity + z_rms * (1.5 + wanderer.get('z_peak_rel_def', 0.1, 0.2)) * (1.0 - defect_severity))
            hf_rms = max(0.0, (wanderer.get('hf_defect', 0.1, 0.8) + 3.75) * defect_severity + z_rms * (0.15 + wanderer.get('hf_rel_def', 0.1, 0.05)) * (1.0 - defect_severity))
            temp_c = ambient_temp + 12.0 + (15.0 + wanderer.get('temp_defect', 0.05, 1.5) + 7.5) * defect_severity
            z_kurtosis = 3.0 + (wanderer.get('z_kurt_defect', 0.15, 1.8) + 8.5) * kurt_severity
            peak_freq = max(0.0, 37.5 + (200.0 - 37.5 + wanderer.get('freq_defect', 0.1, 30.0)) * defect_severity)
        else:
            # Normal healthy running
            z_rms = max(0.5, base_rms)
            z_peak = max(0.0, z_rms * (1.5 + wanderer.get('crest_rel', 0.1, 0.2)) + wanderer.get('crest_noise', 0.2, 0.1))
            hf_rms = max(0.0, z_rms * (0.15 + wanderer.get('hf_rel', 0.1, 0.05)))
            temp_c = ambient_temp + 12.0 + wanderer.get('temp_noise', 0.1, 1.0)
            z_kurtosis = 3.0 + wanderer.get('kurt2', 0.1, 0.2) # Gaussian normal
            peak_freq = max(0.0, 37.5 + wanderer.get('freq_norm', 0.1, 5.0)) # 1x-2x running speed
            
            # Motor slip drops the fundamental running frequency
            if voltage_sag:
                peak_freq = max(0.0, 33.0 + wanderer.get('freq_slip', 0.1, 1.0))

        x_rms = max(0.0, z_rms * (0.7 + wanderer.get('x_rms_rel', 0.1, 0.15)) + wanderer.get('x_rms_noise', 0.2, 0.1))
        x_peak = max(x_rms, z_peak * (0.7 + wanderer.get('x_peak_rel', 0.1, 0.15)) + wanderer.get('x_peak_noise', 0.2, 0.1))
        x_kurtosis = z_kurtosis * (0.85 + wanderer.get('x_kurt_rel', 0.1, 0.1)) + wanderer.get('x_kurt_noise', 0.2, 0.1)

    # 5. Ugly Reality (Benign Glitch) — MUST happen BEFORE derived fields
    # 0.1% chance of a random bump/shock hitting the accelerometer
    if random.random() < 0.001:
        z_rms = 25.0

    # Derived fields computed AFTER glitch so the row is internally consistent
    zone = classify_iso_zone(z_rms)
    z_crest = round(z_peak / max(0.01, z_rms), 2)
    x_crest = round(x_peak / max(0.01, x_rms), 2)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.fromtimestamp(sim_clock.now()).isoformat() + "Z",
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
