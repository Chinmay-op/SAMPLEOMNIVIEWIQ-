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


def generate_reading(is_anomaly: bool = False) -> dict:
    if is_anomaly:
        z_rms = random.uniform(7.5, 18.5)
        x_rms = random.uniform(5.0, 12.0)
        z_peak = random.uniform(1.5, 3.0)
        x_peak = random.uniform(1.0, 2.5)
        hf_rms = random.uniform(1.5, 4.0)
        temp_c = random.uniform(38.0, 58.0) + 15.0
    else:
        z_rms = random.uniform(1.0, 2.8)
        x_rms = random.uniform(0.8, 2.0)
        z_peak = random.uniform(0.1, 0.5)
        x_peak = random.uniform(0.08, 0.4)
        hf_rms = random.uniform(0.1, 0.5)
        temp_c = random.uniform(38.0, 58.0)

    zone = classify_iso_zone(z_rms)

    # --- Kurtosis: derived from ISO zone (Gaussian=3.0, fault=8+) ---
    zone_kurtosis_map = {"ZONE_A": 3.0, "ZONE_B": 4.0, "ZONE_C": 6.0, "ZONE_D": 8.5}
    z_kurtosis = zone_kurtosis_map[zone] + random.uniform(-0.3, 0.3)
    x_kurtosis = z_kurtosis * 0.85 + random.uniform(-0.2, 0.2)

    # --- Crest factor: peak / RMS (direct computation) ---
    z_crest = round(z_peak / hf_rms, 2) if hf_rms > 0 else 3.0
    x_crest = round(x_peak / max(0.01, x_rms * 0.05), 2) if x_rms > 0 else 3.0

    # --- Peak velocity frequency: healthy=running speed, fault=bearing defect ---
    if zone in ["ZONE_A", "ZONE_B"]:
        peak_freq = random.uniform(25.0, 50.0)  # 1x-2x running speed
    else:
        peak_freq = random.uniform(120.0, 300.0)  # bearing defect frequencies

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
    print(f"Starting Vibration Synthetic Data Bot... (Polling {POLL_INTERVAL}s interval)")
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    topic = build_topic("pune-isbm", "compressor-01", "vibration")
    iterations = 0
    with OmniViewMQTTClient() as client:
        while True:
            is_anomaly = (iterations % 30 == 0) and iterations > 0
            payload = generate_reading(is_anomaly)
            validate_payload(payload)
            client.publish(topic, payload)
            print(f"[vibration_bot] Published to {topic} -> {json.dumps(payload)}")
            
            iterations += 1
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
