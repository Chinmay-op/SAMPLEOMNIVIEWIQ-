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

DEVICE_ID = "Selec-MFM384-01"
POLL_INTERVAL = 15
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "electrical_schema.json"

# Load schema once
try:
    with open(SCHEMA_PATH, 'r') as f:
        ELECTRICAL_SCHEMA = json.load(f)
except Exception as e:
    print(f"Warning: Could not load schema from {SCHEMA_PATH}: {e}")
    ELECTRICAL_SCHEMA = None


def validate_payload(payload):
    if ELECTRICAL_SCHEMA and HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=payload, schema=ELECTRICAL_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            print(f"Schema Validation Error: {e.message}")


def generate_reading(is_anomaly: bool = False) -> dict:
    """Fallback generator if no CSV is present."""
    voltage = 415.0 + random.uniform(-2, 2)
    current = 200.0 + random.uniform(-10, 10)
    pf = 0.95 + random.uniform(-0.02, 0.02)
    
    if is_anomaly:
        current += 100.0
        pf -= 0.1

    kw = (voltage * current * pf * 1.732) / 1000
    kva = (voltage * current * 1.732) / 1000
    thd = 3.0 + random.uniform(0, 1)

    # Missing schema fields mapped here
    rolling_kva = kva + random.uniform(-5, 5) # Approximation for edge-computed metric
    md_limit = 150.0 # arbitrary contracted limit
    md_proximity = (rolling_kva / md_limit) * 100

    kvar = (kva**2 - kw**2)**0.5 if kva > kw else 0.0
    energy_base = 150000.0 + random.uniform(0, 100)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "electrical_meter",
        "data": {
            "voltage_v_ln_avg": round(voltage / 1.732, 2),
            "voltage_v_ll_avg": round(voltage, 2),
            "current_a_avg": round(current, 2),
            "active_power_kw_total": round(kw, 2),
            "apparent_power_kva_total": round(kva, 2),
            "reactive_power_kvar_total": round(kvar, 2),
            "power_factor_avg": round(pf, 3),
            "frequency_hz": round(50.0 + random.uniform(-0.2, 0.2), 2),
            "active_energy_kwh": round(energy_base, 2),
            "apparent_energy_kvah": round(energy_base * 1.05, 2),
            "rolling_kva_15min": round(rolling_kva, 2),
            "md_proximity_percent": round(md_proximity, 2)
        }
    }
    return payload


def cast_or_default(value, cast_type, default=0.0):
    try:
        return cast_type(value)
    except (ValueError, TypeError):
        return default


def map_csv_row_to_payload(row):
    """Maps a row from CSV to the strict Selec MFM384 schema structure."""
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
    return payload


from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    csv_path = os.environ.get("ELECTRICAL_CSV_PATH", "data/AV11.csv")
    csv_file = Path(csv_path)

    print(f"Starting Electrical Publisher... (Polling {POLL_INTERVAL}s interval)")
    if csv_file.exists():
        print(f"Mode: CSV Replay ({csv_file})")
    else:
        print(f"Mode: Synthetic Fallback (CSV not found at {csv_file})")

    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    topic = build_topic("pune-isbm", "compressor-01", "electrical")
    iterations = 0
    
    with OmniViewMQTTClient() as client:
        while True:
            # Loop to restart CSV when EOF is reached
            if csv_file.exists():
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        payload = map_csv_row_to_payload(row)
                        validate_payload(payload)
                        client.publish(topic, payload)
                        print(f"[electrical_bot] Published to {topic} -> {json.dumps(payload)}")
                        time.sleep(POLL_INTERVAL) # Pulse every 15s
            else:
                # Fallback Synthetic mode
                is_anomaly = (iterations % 20 == 0) and iterations > 0
                payload = generate_reading(is_anomaly)
                validate_payload(payload)
                client.publish(topic, payload)
                print(f"[electrical_bot] Published to {topic} -> {json.dumps(payload)}")
                iterations += 1
                time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()

