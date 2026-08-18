# ============================================================
# OmniView IQ POC — Gas & Particle Generator (Schneider HeatTag)
# Generates 1-minute gas/particle/thermal data from timeline.
# OUTPUT COLUMNS: Match gas_schema.json exactly (7 fields).
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def compute_severity(gas_ppm, particle_idx):
    """Vectorized severity classification."""
    return np.where(
        (gas_ppm > 80.0) | (particle_idx > 100.0), "CRITICAL",
        np.where(
            (gas_ppm > 30.0) | (particle_idx > 50.0), "ALARM",
            np.where(
                (gas_ppm > 15.0) | (particle_idx > 20.0), "WARNING",
                "NORMAL"
            )
        )
    )

def generate_gas_data():
    print("Generating Gas & Particle data (schema-compliant)...")
    
    # 1. Load Master Timeline
    df = pd.read_parquet("output/master_timeline.parquet")
    total_rows = len(df)
    
    # Initialize arrays
    gas_ppm = np.zeros(total_rows)
    particle_idx = np.zeros(total_rows)
    panel_temp = np.zeros(total_rows)
    rate_of_rise = np.zeros(total_rows)
    
    current_panel_temp = 35.0
    
    state_vals = df["machine_state"].values
    event_vals = df["active_event"].values
    hour_vals = df["timestamp"].dt.hour.values if hasattr(df["timestamp"], "dt") else np.full(total_rows, 12)
    
    print(" -> Simulating gas/particle physics...")
    for i in range(total_rows):
        state = state_vals[i]
        event = event_vals[i]
        hour = hour_vals[i]
        is_running = state in ("NORMAL", "CRITICAL")
        
        # Panel temperature drift
        if is_running:
            current_panel_temp += np.random.uniform(-0.3, 0.4)
        else:
            current_panel_temp -= np.random.uniform(0.05, 0.5)
        current_panel_temp = np.clip(current_panel_temp, 25.0, 50.0)
        
        if event == "PARTICLE_OVERHEATING":
            # Critical overheating scenario
            gas_ppm[i] = np.random.uniform(40.0, 120.0)
            particle_idx[i] = np.random.uniform(50.0, 200.0)
            rise = np.random.uniform(1.5, 5.0)
            current_panel_temp += rise
            rate_of_rise[i] = rise
        elif is_running and np.random.rand() < 0.01:
            # Random warning event (1% chance during operation)
            gas_ppm[i] = np.random.uniform(15.0, 45.0)
            particle_idx[i] = np.random.uniform(20.0, 60.0)
            rise = np.random.uniform(0.5, 2.5)
            current_panel_temp += rise
            rate_of_rise[i] = rise
        else:
            # Normal baseline
            gas_ppm[i] = np.random.uniform(0.0, 1.5)
            particle_idx[i] = np.random.uniform(0.0, 5.0)
            rate_of_rise[i] = np.random.uniform(-0.1, 0.1)
        
        panel_temp[i] = current_panel_temp
    
    # Compute severity
    severity = compute_severity(gas_ppm, particle_idx)
    
    # Compute humidity (rises with severity — thermal moisture release)
    humidity = np.where(
        np.isin(severity, ["ALARM", "CRITICAL"]),
        np.random.uniform(60.0, 82.0, total_rows),
        np.where(
            severity == "WARNING",
            np.random.uniform(50.0, 65.0, total_rows),
            np.random.uniform(38.0, 55.0, total_rows)
        )
    )
    
    # Compute AQI (weighted composite, 0-10 scale)
    aqi = np.minimum(10, (gas_ppm / 10.0 + particle_idx / 25.0).astype(int))
    
    # Format Payload — columns match gas_schema.json
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "gas_particle_sensor",
        "gas_concentration_ppm": np.round(gas_ppm, 2),
        "micro_particle_index": np.round(particle_idx, 2),
        "internal_panel_temp_c": np.round(panel_temp, 1),
        "rate_of_thermal_rise_c_per_min": np.round(rate_of_rise, 2),
        "ambient_humidity_pct": np.round(humidity, 1),
        "air_quality_index": aqi,
        "alert_severity_level": severity,
        "machine_state": df["machine_state"],
        "active_event": df["active_event"],
    })
    
    os.makedirs("output", exist_ok=True)
    payload_df.to_parquet("output/gas_data.parquet")
    payload_df.head(1000).to_csv("output/gas_data_sample.csv", index=False)
    
    print(f"  Generated {len(payload_df):,} gas/particle records (7 schema fields).")
    severity_dist = pd.Series(severity).value_counts()
    for sev, count in severity_dist.items():
        print(f"    {sev}: {count:,} ({count/total_rows*100:.2f}%)")
    
    return payload_df

if __name__ == "__main__":
    generate_gas_data()
