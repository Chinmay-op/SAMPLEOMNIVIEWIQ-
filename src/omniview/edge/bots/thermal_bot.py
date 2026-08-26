import json
import time
import random
import datetime
from pathlib import Path
import sys
from omniview.edge.bots.stochastic import wanderer, PoissonTimer, sim_clock

sys.path.append(str(Path(__file__).resolve().parents[3]))

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
    state["thermal_duty_cycle"] = payload["data"].get("manipulated_variable_mv_heat_percent", 0.0)
    state["thermal_pv"] = payload["data"].get("present_value_pv_c", 25.0)
    state["heater_failed"] = is_anomaly
    
    state_file = Path(".edge_state.json")
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Failed to write edge state: {e}")


# --- Live Stochastic PID State ---
current_pv = 250.0  # Start near setpoint (skip cold-start transient)
integral_error = 0.0
prev_error = 0.0
mv_saturation_streak = 0
last_pv_15m = [250.0] * 15

# Poisson Anomaly Timer
next_anomaly_time = 0.0
anomaly_active_until = 0.0

def get_poisson_anomaly():
    """Uses a Poisson process to trigger thermal anomalies (e.g., Heater Burnout)."""
    global next_anomaly_time, anomaly_active_until
    now = sim_clock.now()
    
    if now < anomaly_active_until:
        return True # Still in anomaly state
        
    if next_anomaly_time == 0.0:
        next_anomaly_time = now + random.expovariate(1.0 / 21600.0) # Mean: 6 hours
        return False
        
    if now >= next_anomaly_time:
        next_anomaly_time = now + random.expovariate(1.0 / 21600.0)
        anomaly_active_until = now + random.uniform(300, 1800) # Burnout lasts 5-30 mins (real heater failures don't self-repair in 60s)
        return True
        
    return False

def generate_reading() -> dict:
    wanderer.end_tick()
    global current_pv, integral_error, prev_error, last_pv_15m, mv_saturation_streak
    
    edge_state = _read_edge_state()
    ambient_temp = edge_state.get("ambient_temp_c", 25.0)
    
    sp = 255.0 # Setpoint
    error = False

    is_anomaly = get_poisson_anomaly()

    # --- Live PID Controller Physics ---
    Kp = 4.0
    Ki = 0.05
    Kd = 1.0
    
    dt = POLL_INTERVAL # 60 seconds
    
    pid_error = sp - current_pv
    integral_error += pid_error * dt
    integral_error = max(-1000, min(integral_error, 1000)) # Anti-windup
    derivative = (pid_error - prev_error) / dt
    
    mv = (Kp * pid_error) + (Ki * integral_error) + (Kd * derivative)
    mv = max(0.0, min(mv, 100.0))
    prev_error = pid_error

    # --- Thermodynamic Physics ---
    # Heat gained from heater vs Heat lost to ambient
    # Calibrated: at 0.06°C/s and cooling_rate 0.0002, equilibrium at 100% duty = ~325°C.
    # PID will settle at 255°C setpoint with MV ≈ 78% duty (realistic).
    heater_power = 0.06 # degrees per second at 100% duty
    ambient_cooling_rate = 0.0002
    
    # Add SSR noise to PID output (always — anomaly or not, the controller still runs)
    mv = max(0.0, min(100.0, mv + wanderer.get('mv', 0.2, 1.0)))
    
    if is_anomaly:
        # Heater burnout: PID still runs and MV climbs naturally toward saturation,
        # but the heating element is physically dead — zero heat generated
        heat_gained = 0.0
    else:
        heat_gained = (mv / 100.0) * heater_power * dt
        
    heat_lost = (current_pv - ambient_temp) * ambient_cooling_rate * dt
    
    # Update actual temperature
    current_pv += (heat_gained - heat_lost)
    
    # 15 min trend
    last_pv_15m.append(current_pv)
    if len(last_pv_15m) > 15:
        last_pv_15m.pop(0)
        
    diff_15m = current_pv - last_pv_15m[0]
    if diff_15m > 5.0:
        trend = "RISING"
    elif diff_15m < -5.0:
        trend = "FALLING"
    else:
        trend = "STABLE"

    # State classification
    if is_anomaly:
        state_str = "HEATING" # Trying to heat, but failing
    elif current_pv < sp - 10:
        state_str = "HEATING"
    else:
        state_str = "AT_SETPOINT"

    # Physics-based heater burnout detection:
    # MV saturated AND temperature stalled/falling (not climbing toward SP)
    mv_saturation_streak = mv_saturation_streak + 1 if mv >= 98.0 else 0
    pv_rate = (heat_gained - heat_lost) / dt if dt > 0 else 0.0  # °C/s
    pv_stalled = pv_rate < 0.001  # effectively not heating
    hb = (mv_saturation_streak >= 2) and (sp - current_pv > 3.0) and pv_stalled
    ssr_fail = hb and (mv >= 99.0) and (random.random() < 0.3)
    # Only flag loop_burnout if PV has genuinely stalled, not just during startup
    loop_burnout = (abs(current_pv - sp) > 30.0) and pv_stalled

    reported_pv = current_pv + random.uniform(-0.5, 0.5)

    payload = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.datetime.fromtimestamp(sim_clock.now()).isoformat() + "Z",
        "sensor_type": "thermal_probe",
        "data": {
            "present_value_pv_c": round(reported_pv, 3),
            "set_point_sp_c": sp,
            "manipulated_variable_mv_heat_percent": round(mv, 2),
            "proportional_band_p": Kp,
            "integral_time_i_sec": Ki,
            "derivative_time_d_sec": Kd,
            "heater_burnout_alarm_hb": hb,
            "ssr_failure_alarm": ssr_fail,
            "loop_burnout_alarm": loop_burnout,
            "temperature_input_error": error,
            "active_sp_number": 0,
            "temp_trend_15min": trend,
            "machine_thermal_state": state_str
        }
    }
    
    _write_edge_state(payload, is_anomaly)
    return payload


from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

def run_bot():
    print(f"Starting Thermal Live Stochastic Bot... (Polling {POLL_INTERVAL}s interval)")
    print("Mode: True Stochastic Live Generation (PID Loop + Poisson Anomalies + Shared State)")
    
    topic = build_topic("pune-isbm", "compressor-01", "thermal")
    with OmniViewMQTTClient() as client:
        while True:
            payload = generate_reading()
            validate_payload(payload)
            client.publish(topic, payload)
            
            pv = payload["data"]["present_value_pv_c"]
            mv = payload["data"]["manipulated_variable_mv_heat_percent"]
            print(f"[thermal_bot] Published -> Temp: {pv}C | Duty Cycle: {mv}%")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
