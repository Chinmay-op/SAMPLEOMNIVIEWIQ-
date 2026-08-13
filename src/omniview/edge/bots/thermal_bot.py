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

DEVICE_ID = "Omron-E5CC-01"
POLL_INTERVAL = 60
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "schemas" / "thermal_schema.json"

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


# Global state for thermal lifecycle simulation
state_cycle = "AT_SETPOINT"
current_pv = 255.0


def generate_reading(is_anomaly: bool = False) -> dict:
    global state_cycle, current_pv

    sp = 255.0
    hb = False
    error = False

    if is_anomaly:
        state_cycle = "AT_SETPOINT" # Anomaly overrides normal state progression for this poll
        pv = round(random.uniform(275.5, 300.0), 1)
        mv = 100.0
        hb = True
        trend = "RISING"
        state_str = "AT_SETPOINT"
    else:
        if state_cycle == "HEATING":
            # Ramp up 4.5 C/min
            current_pv = min(255.0, current_pv + 4.5)
            pv = round(current_pv + random.uniform(-0.5, 0.5), 1)
            mv = round(random.uniform(85.0, 100.0), 1)
            trend = "RISING"
            state_str = "HEATING"
            if current_pv >= 250.0:
                state_cycle = "AT_SETPOINT"
                
        elif state_cycle == "IDLE_HOT":
            # Idle
            pv = round(random.uniform(240.0, 260.0), 1)
            mv = round(random.uniform(15.0, 35.0), 1)
            trend = random.choice(["STABLE", "FALLING"])
            state_str = "IDLE_HOT"
            
        else: # AT_SETPOINT
            pv = round(random.uniform(247.0, 263.0), 1)
            mv = round(random.uniform(30.0, 60.0), 1)
            trend = "STABLE"
            state_str = "AT_SETPOINT"

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "sensor_type": "thermal_probe",
        "data": {
            "present_value_pv_c": pv,
            "set_point_sp_c": sp,
            "manipulated_variable_mv_heat_percent": mv,
            "heater_burnout_alarm_hb": hb,
            "temperature_input_error": error,
            "temp_trend_15min": trend,
            "machine_thermal_state": state_str
        }
    }
    return payload

def run_bot():
    global state_cycle, current_pv
    print(f"Starting Thermal Synthetic Data Bot... (Polling {POLL_INTERVAL}s interval)")
    if not HAS_JSONSCHEMA:
        print("Warning: 'jsonschema' package not installed. Strict payload validation is disabled.")
    
    # Start cold
    current_pv = 25.0
    state_cycle = "HEATING"
    
    iterations = 0
    while True:
        # Occasionally simulate idle
        if iterations % 50 == 40:
            state_cycle = "IDLE_HOT"
        elif iterations % 50 == 0 and iterations > 0:
            state_cycle = "HEATING"
            current_pv = 150.0 # Reheat from idle
            
        is_anomaly = (iterations % 45 == 0) and iterations > 0
        
        payload = generate_reading(is_anomaly)
        validate_payload(payload)
        print(json.dumps(payload))
        
        iterations += 1
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
