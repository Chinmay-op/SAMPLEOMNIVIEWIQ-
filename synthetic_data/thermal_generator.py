# ============================================================
# OmniView IQ POC — Thermal Generator (Omron E5CC)
# Polls every 60 seconds. Simulates thermal mass (heating/cooling).
# OUTPUT COLUMNS: Match thermal_schema.json exactly (13 fields).
# Cross-sensor: reads electrical state for IDLE_HOT detection.
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def generate_thermal_data():
    print("Generating Thermal data (schema-compliant)...")
    cfg = LAYER_0["thermal"]
    
    # 1. Load Master Timeline (1 min resolution)
    df = pd.read_parquet("output/master_timeline.parquet")
    total_rows = len(df)
    
    # 2. Load Ambient Data (2 min resolution -> upsample to 1 min)
    ambient_df = pd.read_parquet("output/ambient_data.parquet")
    ambient_df.set_index("timestamp", inplace=True)
    ambient_upsampled = ambient_df.resample("1min").ffill().reset_index()
    df = pd.merge(df, ambient_upsampled[["timestamp", "ambient_temp_c"]], on="timestamp", how="left")
    df["ambient_temp_c"] = df["ambient_temp_c"].ffill().bfill()
    
    # 3. Load Electrical cross-sensor state (15s -> downsample to 1 min)
    try:
        elec_df = pd.read_parquet("output/electrical_cross_sensor.parquet")
        elec_df.set_index("timestamp", inplace=True)
        elec_1min = elec_df.resample("1min").mean().reset_index()
        df = pd.merge(df, elec_1min[["timestamp", "current_a_avg"]], on="timestamp", how="left")
        df["current_a_avg"] = df["current_a_avg"].ffill().bfill().fillna(0.0)
    except Exception:
        df["current_a_avg"] = 0.0
    
    # Initialize arrays
    pv = np.zeros(total_rows)           # Present Value (actual temp)
    mv = np.zeros(total_rows)           # Manipulated Variable (heater duty %)
    thermal_state = np.empty(total_rows, dtype=object)
    hb_alarm = np.zeros(total_rows, dtype=bool)
    ssr_alarm = np.zeros(total_rows, dtype=bool)
    loop_alarm = np.zeros(total_rows, dtype=bool)
    temp_error = np.zeros(total_rows, dtype=bool)
    active_sp = np.zeros(total_rows, dtype=int)
    
    # Constants
    sp = cfg["barrel_setpoint_c"]        # 255.0
    lazy_idle_threshold = cfg["lazy_idle_temp_threshold_c"]  # 240.0
    heat_rate = cfg["heat_up_rate_c_per_min"]   # 4.5
    p_band = 5.0
    i_time = 240
    d_time = 60
    
    current_temp = df["ambient_temp_c"].values[0]  # Start cold
    
    state_vals = df["machine_state"].values
    event_vals = df["active_event"].values
    ambient_vals = df["ambient_temp_c"].values
    current_a_vals = df["current_a_avg"].values
    
    print(" -> Simulating thermal mass physics with cross-sensor correlation...")
    for i in range(total_rows):
        state = state_vals[i]
        event = event_vals[i]
        ambient = ambient_vals[i]
        elec_i = current_a_vals[i]
        
        # === State machine ===
        if state == "POWER_OFF":
            diff = current_temp - ambient
            if diff > 0:
                current_temp -= max(0.1, diff * 0.005)
            t_state = "COOLING"
            mv_val = 0.0
            
        elif state == "IDLE" or event == "COLD_START":
            if event == "LAZY_IDLE" or (current_temp > lazy_idle_threshold and elec_i < 50.0):
                # Cross-sensor: heaters on but machine not producing
                if current_temp < sp:
                    current_temp += heat_rate * 0.3
                t_state = "IDLE_HOT"
                mv_val = round(np.random.uniform(15.0, 35.0), 1)
            elif event == "COLD_START":
                current_temp += heat_rate
                t_state = "HEATING"
                mv_val = round(np.random.uniform(85.0, 100.0), 1)
            else:
                diff = current_temp - ambient
                if diff > 0:
                    current_temp -= max(0.1, diff * 0.005)
                t_state = "COOLING"
                mv_val = 0.0
                
        elif state == "NORMAL" or state == "CRITICAL":
            if current_temp < sp - 2.0:
                current_temp += heat_rate
                t_state = "HEATING"
                mv_val = round(np.random.uniform(70.0, 100.0), 1)
            else:
                current_temp = sp + np.random.uniform(-3.0, 3.0)
                t_state = "AT_SETPOINT"
                mv_val = round(np.random.uniform(30.0, 60.0), 1)
                
            # Heater burnout scenario
            if event == "THERMAL_INSTABILITY":
                current_temp += 3.0
                t_state = "HEATING"
                mv_val = 100.0
                hb_alarm[i] = True
        else:
            t_state = "COOLING"
            mv_val = 0.0
                
        pv[i] = current_temp
        mv[i] = mv_val
        thermal_state[i] = t_state
        
        # Alarm logic
        ssr_alarm[i] = hb_alarm[i] and mv_val >= 99.0
        loop_alarm[i] = abs(current_temp - sp) > 30.0
        active_sp[i] = 1 if t_state == "IDLE_HOT" else 0
    
    # Add sensor noise
    noise = np.random.normal(0, cfg["noise_temp_abs"], total_rows)
    pv = np.round(pv + noise, 1)
    mv = np.round(mv, 1)
    
    # Compute trend
    pv_series = pd.Series(pv)
    temp_diff = pv_series.diff(15)
    trend = np.where(temp_diff > 5.0, "RISING", np.where(temp_diff < -5.0, "FALLING", "STABLE"))
    
    # Final IDLE_HOT override using cross-sensor truth
    machine_state_vals = df["machine_state"].values
    for i in range(total_rows):
        if machine_state_vals[i] == "IDLE" and pv[i] > lazy_idle_threshold:
            thermal_state[i] = "IDLE_HOT"
            active_sp[i] = 1
    
    # Format Payload — columns match thermal_schema.json
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "thermal_probe",
        "present_value_pv_c": pv,
        "set_point_sp_c": sp,
        "manipulated_variable_mv_heat_percent": mv,
        "proportional_band_p": p_band,
        "integral_time_i_sec": i_time,
        "derivative_time_d_sec": d_time,
        "heater_burnout_alarm_hb": hb_alarm,
        "ssr_failure_alarm": ssr_alarm,
        "loop_burnout_alarm": loop_alarm,
        "temperature_input_error": temp_error,
        "active_sp_number": active_sp,
        "temp_trend_15min": trend,
        "machine_thermal_state": thermal_state,
        "machine_state": df["machine_state"],
        "active_event": df["active_event"],
    })
    
    payload_df.to_parquet("output/thermal_data.parquet")
    payload_df.head(1000).to_csv("output/thermal_data_sample.csv", index=False)
    
    print(f"  Generated {len(payload_df):,} thermal records (13 schema fields).")
    
    return payload_df

if __name__ == "__main__":
    generate_thermal_data()
