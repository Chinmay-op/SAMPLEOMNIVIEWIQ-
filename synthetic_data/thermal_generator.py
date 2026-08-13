# ============================================================
# OmniView IQ POC — Thermal Generator
# Polls every 60 seconds. Simulates thermal mass (heating/cooling).
# Dependent on Ambient generator for baseline decay limits.
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def generate_thermal_data():
    print("Generating Thermal data...")
    cfg = LAYER_0["thermal"]
    
    # 1. Load Master Timeline (1 min resolution)
    df = pd.read_parquet("output/master_timeline.parquet")
    total_rows = len(df)
    
    # 2. Load Ambient Data (2 min resolution -> upsample to 1 min)
    ambient_df = pd.read_parquet("output/ambient_data.parquet")
    ambient_df.set_index("timestamp", inplace=True)
    ambient_upsampled = ambient_df.resample("1min").ffill().reset_index()
    
    # Merge timelines
    df = pd.merge(df, ambient_upsampled[["timestamp", "ambient_temp_c"]], on="timestamp", how="left")
    df["ambient_temp_c"] = df["ambient_temp_c"].ffill().bfill()
    
    # Initialize thermal values
    surface_temp = np.zeros(total_rows)
    thermal_state = np.empty(total_rows, dtype=object)
    
    # Physics parameters
    target_temp = cfg["barrel_setpoint_c"]       # 255.0
    lazy_idle_threshold = cfg["lazy_idle_temp_threshold_c"]  # 240.0
    
    # Heat up / cool down rates (degrees per minute)
    heat_rate = 2.0
    cool_rate = -0.5
    
    current_temp = df["ambient_temp_c"].iloc[0] # Start at ambient
    
    print(" -> Simulating thermal mass physics...")
    # 3. Simulate Thermal Mass
    for i in range(total_rows):
        state = df["machine_state"].iloc[i]
        event = df["active_event"].iloc[i]
        ambient = df["ambient_temp_c"].iloc[i]
        
        # State: POWER_OFF
        if state == "POWER_OFF":
            # Cooldown curve: decays towards ambient
            diff = current_temp - ambient
            if diff > 0:
                # Newton's law of cooling approximation
                current_temp -= max(0.1, diff * 0.005) 
            t_state = "COOLING"
            
        # State: IDLE / COLD_START
        elif state == "IDLE" or event == "COLD_START":
            if event == "LAZY_IDLE":
                # Heater bands are on, but machine not producing
                if current_temp < target_temp:
                    current_temp += heat_rate
                else:
                    current_temp = target_temp
                t_state = "IDLE_HOT"
            else:
                # Normal idle (heaters off or standby)
                diff = current_temp - ambient
                if diff > 0:
                    current_temp -= max(0.1, diff * 0.005)
                t_state = "COOLING"
                
        # State: NORMAL Production
        elif state == "NORMAL":
            if current_temp < target_temp - 2.0:
                current_temp += heat_rate
                t_state = "HEATING"
            else:
                # Oscillate around setpoint
                t_state = "AT_SETPOINT"
                
        # State: CRITICAL (Over temp scenario)
        elif state == "CRITICAL" and event == "THERMAL_INSTABILITY":
            # Heater runaway
            current_temp += 3.0
            t_state = "HEATING"
        elif state == "CRITICAL":
            # Behave like normal for other events
            if current_temp < target_temp - 2.0:
                current_temp += heat_rate
                t_state = "HEATING"
            else:
                t_state = "AT_SETPOINT"
                
        surface_temp[i] = current_temp
        thermal_state[i] = t_state
        
    df["surface_temperature_c"] = surface_temp
    df["machine_thermal_state"] = thermal_state
    
    # 4. Add Sensor Noise
    noise = np.random.normal(0, cfg["noise_temp_abs"], total_rows)
    df["surface_temperature_c"] = np.round(df["surface_temperature_c"] + noise, 2)
    
    # 5. Compute Edge-Derived Trend (15-min rolling slope)
    print(" -> Computing Edge thermal trends...")
    df["temp_diff_15min"] = df["surface_temperature_c"].diff(15)
    
    df["temp_trend_15min"] = np.where(
        df["temp_diff_15min"] > 5.0, "RISING",
        np.where(df["temp_diff_15min"] < -5.0, "FALLING", "STABLE")
    )
    
    # Refine Lazy Idle flag using real logic (Current low + Temp high)
    # Since we don't have exact current here, we proxy it from the timeline state.
    # A real gateway would check: (electrical.current < threshold) AND (thermal.temp > 240)
    df["machine_thermal_state"] = np.where(
        (df["machine_state"] == "IDLE") & (df["surface_temperature_c"] > lazy_idle_threshold),
        "IDLE_HOT",
        df["machine_thermal_state"]
    )
    
    # 6. Format Payload
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "thermal_probe",
        "surface_temperature_c": df["surface_temperature_c"],
        "temp_trend_15min": df["temp_trend_15min"],
        "machine_thermal_state": df["machine_thermal_state"],
        "machine_state": df["machine_state"], # Ground truth
        "active_event": df["active_event"]    # Ground truth
    })
    
    payload_df.to_parquet("output/thermal_data.parquet")
    payload_df.head(1000).to_csv("output/thermal_data_sample.csv", index=False)
    
    print(f"✅ Generated {len(payload_df):,} thermal records.")
    
    return payload_df

if __name__ == "__main__":
    generate_thermal_data()
