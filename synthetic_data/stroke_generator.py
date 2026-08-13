# ============================================================
# OmniView IQ POC — Stroke Counter Generator
# Generates digital pulse data (strokes per minute) based on 
# the machine's production state in the master timeline.
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def generate_stroke_data():
    print("Generating Stroke Counter data...")
    cfg = LAYER_0["stroke"]
    
    # 1. Load Master Timeline (1 min resolution)
    df = pd.read_parquet("output/master_timeline.parquet")
    total_rows = len(df)
    
    # Initialize arrays
    strokes_in_interval = np.zeros(total_rows, dtype=int)
    last_cycle_time = np.full(total_rows, np.nan)
    
    nominal_cycle_time = cfg["nominal_cycle_time_s"]
    variance = cfg["cycle_time_variance_s"]
    
    print(" -> Simulating production cycles...")
    for i in range(total_rows):
        state = df["machine_state"].iloc[i]
        
        if state == "NORMAL":
            # Determine actual cycle time for this minute
            cycle_time = np.random.normal(nominal_cycle_time, variance)
            
            # How many strokes fit in a 60-second window?
            strokes = int(60.0 / cycle_time)
            
            # Occasional extra delay (micro-stops) might reduce stroke count
            if np.random.rand() < 0.05:
                strokes = max(0, strokes - 1)
                cycle_time += 10.0 # Reflects a slow cycle
                
            strokes_in_interval[i] = strokes
            last_cycle_time[i] = round(cycle_time, 2)
            
        elif state == "CRITICAL" and df["active_event"].iloc[i] == "THERMAL_INSTABILITY":
            # Machine might be struggling, cycles slower
            cycle_time = nominal_cycle_time + 8.0
            strokes = int(60.0 / cycle_time)
            strokes_in_interval[i] = strokes
            last_cycle_time[i] = round(cycle_time, 2)
            
        else:
            # IDLE, POWER_OFF, or other non-producing states
            strokes_in_interval[i] = 0
            last_cycle_time[i] = np.nan
            
    # Calculate cumulative total strokes
    total_strokes = np.cumsum(strokes_in_interval)
    
    # Format Payload
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "digital_pulse_counter",
        "total_strokes": total_strokes,
        "strokes_in_interval": strokes_in_interval,
        "last_cycle_time_seconds": last_cycle_time,
        "machine_state": df["machine_state"] # Ground truth
    })
    
    os.makedirs("output", exist_ok=True)
    payload_df.to_parquet("output/stroke_data.parquet")
    payload_df.head(1000).to_csv("output/stroke_data_sample.csv", index=False)
    
    print(f"✅ Generated {len(payload_df):,} stroke counter records.")
    print(f"   Total strokes accumulated over 1 year: {total_strokes[-1]:,}")
    
    return payload_df

if __name__ == "__main__":
    generate_stroke_data()
