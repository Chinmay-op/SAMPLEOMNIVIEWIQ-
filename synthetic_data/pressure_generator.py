# ============================================================
# OmniView IQ POC — Pneumatic Pressure Generator
# Generates the 28-36 bar compressor cycle and leak scenarios.
# CRITICAL: Also exports the compressor load state timeline 
# so the electrical generator can sync its power spikes.
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def generate_pressure_data():
    print("Generating Pneumatic Pressure data...")
    cfg = LAYER_0["pressure"]
    
    # 1. Read the master timeline
    timeline_df = pd.read_parquet("output/master_timeline.parquet")
    
    # Pressure is polled every 60 seconds, which matches the 1-minute timeline resolution exactly.
    df = timeline_df.copy()
    total_rows = len(df)
    
    # Initialize columns
    df["pressure_bar"] = 0.0
    df["compressor_state"] = "OFF"
    df["decay_rate_bar_min"] = 0.0
    df["pressure_trend_5min"] = "STABLE"
    
    # Physics parameters
    target_max = cfg["normal_band_max_bar"]  # 36.0 (Unload point)
    target_min = cfg["normal_band_min_bar"]  # 28.0 (Load point)
    normal_decay = -0.15                     # bar/min when unloaded (normal usage)
    leak_decay = cfg["leak_decay_threshold_bar_per_min"] - 0.2 # Severely negative for leak
    pump_rate = 3.0                          # bar/min when loaded
    
    current_pressure = 0.0
    
    pressure_values = np.zeros(total_rows)
    state_values = np.empty(total_rows, dtype=object)
    
    # 2. Iterate through timeline to simulate the mechanical cycle
    for i in range(total_rows):
        state = df["machine_state"].iloc[i]
        event = df["active_event"].iloc[i]
        
        # State: POWER_OFF
        if state == "POWER_OFF":
            current_pressure = max(0.0, current_pressure - 0.05) # Slow bleed to 0
            comp_state = "OFF"
            
        # State: IDLE / COLD_START
        elif state == "IDLE" or event == "COLD_START":
            if current_pressure < target_min:
                comp_state = "LOADED"
                current_pressure = min(target_max, current_pressure + pump_rate)
            else:
                comp_state = "UNLOADED"
                # Even idle factories use a tiny bit of air (pilot valves etc)
                current_pressure = max(target_min - 1.0, current_pressure - 0.02)
                
        # State: NORMAL Production
        elif state == "NORMAL":
            if current_pressure <= target_min:
                comp_state = "LOADED"
            elif current_pressure >= target_max:
                comp_state = "UNLOADED"
            else:
                # Keep previous state if in between
                comp_state = state_values[i-1] if i > 0 else "UNLOADED"
            
            if comp_state == "LOADED":
                current_pressure = min(target_max, current_pressure + pump_rate)
            else:
                # Normal usage decay
                current_pressure = max(0.0, current_pressure + normal_decay)
                
        # State: CRITICAL Scenarios
        elif state == "CRITICAL":
            if event == "PNEUMATIC_LEAK":
                comp_state = "UNLOADED" # Force unload so decay is visible
                current_pressure = max(0.0, current_pressure + leak_decay)
            elif event == "COMPRESSOR_INEFFICIENCY":
                comp_state = "LOADED"
                # Fails to pump efficiently, pressure drops despite running
                current_pressure = max(0.0, current_pressure - 0.1)
            else:
                # Just act NORMAL for other unrelated critical events (like MD Breach)
                if current_pressure <= target_min:
                    comp_state = "LOADED"
                elif current_pressure >= target_max:
                    comp_state = "UNLOADED"
                else:
                    comp_state = state_values[i-1] if i > 0 else "UNLOADED"
                
                if comp_state == "LOADED":
                    current_pressure += pump_rate
                else:
                    current_pressure += normal_decay
        
        pressure_values[i] = current_pressure
        state_values[i] = comp_state

    df["pressure_bar"] = pressure_values
    df["compressor_state"] = state_values
    
    # 3. Add Sensor Noise
    noise = np.random.normal(0, cfg["noise_pressure_abs"], total_rows)
    df["pressure_bar"] = np.round(np.clip(df["pressure_bar"] + noise, 0.0, 45.0), 2)
    
    # 4. Compute Edge Derived Fields (decay rate & trend)
    # Using a 5-minute rolling window to compute slope
    df["decay_rate_bar_min"] = df["pressure_bar"].diff(5) / 5.0
    df["decay_rate_bar_min"] = df["decay_rate_bar_min"].fillna(0).round(2)
    
    df["pressure_trend_5min"] = np.where(
        df["decay_rate_bar_min"] > 0.1, "RISING",
        np.where(df["decay_rate_bar_min"] < -0.1, "FALLING", "STABLE")
    )
    
    # 5. Format Payload
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "pressure_transmitter",
        "pressure_bar": df["pressure_bar"],
        "decay_rate_bar_min": df["decay_rate_bar_min"],
        "compressor_state": df["compressor_state"],
        "pressure_trend_5min": df["pressure_trend_5min"],
        "machine_state": df["machine_state"], # Ground truth label
        "active_event": df["active_event"]    # Ground truth label
    })
    
    os.makedirs("output", exist_ok=True)
    payload_df.to_parquet("output/pressure_data.parquet")
    payload_df.head(1000).to_csv("output/pressure_data_sample.csv", index=False)
    
    # 6. EXPORT COMPRESSOR TIMELINE FOR ELECTRICAL SENSOR
    # The electrical generator MUST read this file to know when to spike current
    comp_sync_df = payload_df[["timestamp", "compressor_state"]]
    comp_sync_df.to_parquet("output/compressor_sync.parquet")
    
    print(f"✅ Generated {len(payload_df):,} pressure records.")
    print("✅ Exported compressor sync timeline for Electrical Generator.")
    
    return payload_df

if __name__ == "__main__":
    generate_pressure_data()
