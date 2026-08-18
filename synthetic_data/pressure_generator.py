# ============================================================
# OmniView IQ POC — Pneumatic Pressure Generator (Festo SPAU)
# Generates the 28-36 bar compressor cycle and leak scenarios.
# OUTPUT COLUMNS: Match pressure_schema.json exactly (13 fields).
# CRITICAL: Also exports the compressor load state timeline
# so the electrical generator can sync its power spikes.
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

TEACH_SP1 = 25.0  # Low-pressure alarm threshold
TEACH_SP2 = 18.0  # Critical-low threshold

def bar_to_raw(pressure_bar: float) -> int:
    """Convert bar to Festo SPAU 14-bit ADC raw value (0-16383 over 0-40 bar)."""
    return int(np.clip((pressure_bar / 40.0) * 16383, 0, 16383))

def generate_pressure_data():
    print("Generating Pneumatic Pressure data (schema-compliant)...")
    cfg = LAYER_0["pressure"]
    
    # 1. Read the master timeline
    timeline_df = pd.read_parquet("output/master_timeline.parquet")
    df = timeline_df.copy()
    total_rows = len(df)
    
    # Physics parameters
    target_max = cfg["normal_band_max_bar"]   # 36.0 (Unload point)
    target_min = cfg["normal_band_min_bar"]   # 28.0 (Load point)
    normal_decay = -0.15                      # bar/min when unloaded
    leak_decay = cfg["leak_decay_threshold_bar_per_min"] - 0.2
    pump_rate = 3.0                           # bar/min when loaded
    
    current_pressure = 0.0
    pressure_values = np.zeros(total_rows)
    state_values = np.empty(total_rows, dtype=object)
    pressure_min_memory = 999.0
    pressure_max_memory = 0.0
    min_mem_arr = np.zeros(total_rows)
    max_mem_arr = np.zeros(total_rows)
    
    state_vals = df["machine_state"].values
    event_vals = df["active_event"].values
    
    # 2. Simulate mechanical cycle
    print(" -> Simulating compressor load/unload cycle...")
    for i in range(total_rows):
        state = state_vals[i]
        event = event_vals[i]
        
        if state == "POWER_OFF":
            current_pressure = max(0.0, current_pressure - 0.05)
            comp_state = "OFF"
        elif state == "IDLE" or event == "COLD_START":
            if current_pressure < target_min:
                comp_state = "LOADED"
                current_pressure = min(target_max, current_pressure + pump_rate)
            else:
                comp_state = "UNLOADED"
                current_pressure = max(target_min - 1.0, current_pressure - 0.02)
        elif state == "NORMAL":
            if current_pressure <= target_min:
                comp_state = "LOADED"
            elif current_pressure >= target_max:
                comp_state = "UNLOADED"
            else:
                comp_state = state_values[i-1] if i > 0 else "UNLOADED"
            if comp_state == "LOADED":
                current_pressure = min(target_max, current_pressure + pump_rate)
            else:
                current_pressure = max(0.0, current_pressure + normal_decay)
        elif state == "CRITICAL":
            if event == "PNEUMATIC_LEAK":
                comp_state = "UNLOADED"
                current_pressure = max(0.0, current_pressure + leak_decay)
            else:
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
        else:
            comp_state = "OFF"
        
        pressure_values[i] = current_pressure
        state_values[i] = comp_state
        
        # Running min/max memory
        if current_pressure > 0.1:
            pressure_min_memory = min(pressure_min_memory, current_pressure)
        pressure_max_memory = max(pressure_max_memory, current_pressure)
        min_mem_arr[i] = pressure_min_memory
        max_mem_arr[i] = pressure_max_memory
    
    # 3. Add Sensor Noise
    noise = np.random.normal(0, cfg["noise_pressure_abs"], total_rows)
    pressure_bar = np.round(np.clip(pressure_values + noise, 0.0, 45.0), 2)
    
    # 4. Compute all schema fields
    process_data_raw = np.array([bar_to_raw(p) for p in pressure_bar])
    internal_temp = np.round(np.random.uniform(28.0, 40.0, total_rows), 1)
    switching_out1 = pressure_bar < TEACH_SP1
    switching_out2 = pressure_bar < TEACH_SP2
    device_status = np.where(pressure_bar < TEACH_SP2, 1, 0)
    
    # 5. Compute trend
    pressure_series = pd.Series(pressure_bar)
    decay_rate = (pressure_series.diff(5) / 5.0).fillna(0).round(2).values
    trend = np.where(decay_rate > 0.1, "RISING", np.where(decay_rate < -0.1, "FALLING", "STABLE"))
    
    # 6. Format Payload — columns match pressure_schema.json
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "pressure_transmitter",
        "process_data_variable_raw": process_data_raw,
        "pressure_bar": pressure_bar,
        "pressure_unit": "bar",
        "pressure_min_memory_bar": np.round(min_mem_arr, 2),
        "pressure_max_memory_bar": np.round(max_mem_arr, 2),
        "teach_sp1_bar": TEACH_SP1,
        "teach_sp2_bar": TEACH_SP2,
        "switching_output_1_active": switching_out1,
        "switching_output_2_active": switching_out2,
        "device_status_code": device_status,
        "internal_temperature_c": internal_temp,
        "compressor_state": state_values,
        "pressure_trend_5min": trend,
        "machine_state": df["machine_state"],
        "active_event": df["active_event"],
    })
    
    os.makedirs("output", exist_ok=True)
    payload_df.to_parquet("output/pressure_data.parquet")
    payload_df.head(1000).to_csv("output/pressure_data_sample.csv", index=False)
    
    # 7. EXPORT COMPRESSOR TIMELINE FOR ELECTRICAL SENSOR
    comp_sync_df = payload_df[["timestamp", "compressor_state"]]
    comp_sync_df.to_parquet("output/compressor_sync.parquet")
    
    print(f"  Generated {len(payload_df):,} pressure records (13 schema fields).")
    print("  Exported compressor sync timeline for Electrical Generator.")
    
    return payload_df

if __name__ == "__main__":
    generate_pressure_data()
