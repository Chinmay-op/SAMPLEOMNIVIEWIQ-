# ============================================================
# OmniView IQ POC — Stroke Counter Generator (Sick IME)
# Generates digital pulse data (strokes per minute) based on
# the machine's production state in the master timeline.
# OUTPUT COLUMNS: Match stroke_schema.json exactly (10 fields).
# Cross-sensor: strokes = 0 when electrical power is off.
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def generate_stroke_data():
    print("Generating Stroke Counter data (schema-compliant)...")
    cfg = LAYER_0["stroke"]
    
    # 1. Load Master Timeline (1 min resolution)
    df = pd.read_parquet("output/master_timeline.parquet")
    total_rows = len(df)
    
    # 2. Load electrical cross-sensor state for correlation
    try:
        elec_df = pd.read_parquet("output/electrical_cross_sensor.parquet")
        elec_df.set_index("timestamp", inplace=True)
        elec_1min = elec_df.resample("1min").mean().reset_index()
        df = pd.merge(df, elec_1min[["timestamp", "current_a_avg"]], on="timestamp", how="left")
        df["current_a_avg"] = df["current_a_avg"].ffill().bfill().fillna(0.0)
    except Exception:
        df["current_a_avg"] = np.where(df["machine_state"] == "NORMAL", 400.0, 0.0)
    
    nominal_cycle_time = cfg["nominal_cycle_time_s"]
    variance = cfg["cycle_time_variance_s"]
    
    # Initialize arrays
    strokes = np.zeros(total_rows, dtype=int)
    cycle_time = np.full(total_rows, 0.0)
    signal_quality = np.full(total_rows, 250, dtype=int)
    device_temp = np.zeros(total_rows)
    bdc1 = np.zeros(total_rows, dtype=bool)
    
    state_vals = df["machine_state"].values
    event_vals = df["active_event"].values
    current_a_vals = df["current_a_avg"].values
    
    print(" -> Simulating production cycles with cross-sensor correlation...")
    for i in range(total_rows):
        state = state_vals[i]
        event = event_vals[i]
        elec_i = current_a_vals[i]
        
        if state == "NORMAL" and elec_i > 50.0:
            ct = np.random.normal(nominal_cycle_time, variance)
            s = int(60.0 / ct)
            
            # Micro-stops
            if np.random.rand() < 0.05:
                s = max(0, s - 1)
                ct += 10.0
            
            # Stroke rate drop event
            if event == "STROKE_RATE_DROP":
                ct += 8.0
                s = max(1, int(60.0 / ct))
                signal_quality[i] = np.random.randint(180, 220)
            
            strokes[i] = s
            cycle_time[i] = round(ct, 2)
            signal_quality[i] = np.random.randint(240, 255) if signal_quality[i] > 230 else signal_quality[i]
            bdc1[i] = np.random.rand() < 0.20
            device_temp[i] = 28.0 + np.random.uniform(0, 7.0)
            
        elif state == "CRITICAL" and elec_i > 50.0:
            ct = nominal_cycle_time + 5.0
            s = int(60.0 / ct)
            strokes[i] = s
            cycle_time[i] = round(ct, 2)
            signal_quality[i] = np.random.randint(200, 240)
            bdc1[i] = np.random.rand() < 0.15
            device_temp[i] = 30.0 + np.random.uniform(0, 5.0)
        else:
            # IDLE, POWER_OFF, or no electrical power -> no strokes
            strokes[i] = 0
            cycle_time[i] = 0.0
            signal_quality[i] = np.random.randint(245, 255)
            bdc1[i] = False
            device_temp[i] = 28.0 + np.random.uniform(0, 3.0)
    
    # Derived fields
    counter_value = np.cumsum(strokes) + 1500000  # Start from existing counter
    bdc2 = ~bdc1
    operating_hours = np.arange(total_rows) / 60 + 8000  # Cumulative hours
    sensing_margin = np.round((signal_quality / 255.0) * 100.0, 1)
    device_status = np.where(signal_quality > 180, 0, 1)
    
    # Format Payload — columns match stroke_schema.json
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "digital_pulse_counter",
        "switching_state_bdc1": bdc1,
        "switching_state_bdc2": bdc2,
        "counter_value": counter_value,
        "device_temperature_c": np.round(device_temp, 1),
        "operating_hours": operating_hours.astype(int),
        "signal_quality": signal_quality,
        "sensing_distance_margin_pct": sensing_margin,
        "device_status_code": device_status,
        "strokes_in_interval": strokes,
        "last_cycle_time_seconds": cycle_time,
        "machine_state": df["machine_state"],
        "active_event": df["active_event"],
    })
    
    os.makedirs("output", exist_ok=True)
    payload_df.to_parquet("output/stroke_data.parquet")
    payload_df.head(1000).to_csv("output/stroke_data_sample.csv", index=False)
    
    print(f"  Generated {len(payload_df):,} stroke records (10 schema fields).")
    print(f"  Total strokes over 1 year: {counter_value[-1] - 1500000:,}")
    
    return payload_df

if __name__ == "__main__":
    generate_stroke_data()
