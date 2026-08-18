# ============================================================
# OmniView IQ POC — Vibration Generator (Banner QM30VT1)
# Polls every 60 seconds. Simulates mechanical wear over
# 14+ day degradation windows (Zone A -> D).
# OUTPUT COLUMNS: Match vibration_schema.json exactly (13 fields).
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def classify_iso_zone(z_rms):
    """Vectorized ISO 10816-3 zone classification."""
    return np.where(z_rms <= 2.8, "ZONE_A",
           np.where(z_rms <= 7.1, "ZONE_B",
           np.where(z_rms <= 18.0, "ZONE_C", "ZONE_D")))

def generate_vibration_data():
    print("Generating Vibration data (schema-compliant)...")
    cfg = LAYER_0["vibration"]
    
    # 1. Load Master Timeline
    df = pd.read_parquet("output/master_timeline.parquet")
    total_rows = len(df)
    
    # 2. Extract physics params
    base_rms_normal = 1.5
    degradation_impact_max = 5.5
    
    # Initialize arrays
    z_rms = np.zeros(total_rows)
    x_rms = np.zeros(total_rows)
    z_peak_g = np.zeros(total_rows)
    x_peak_g = np.zeros(total_rows)
    hf_rms_g = np.zeros(total_rows)
    temp_c = np.zeros(total_rows)
    
    state_vals = df["machine_state"].values
    event_vals = df["active_event"].values
    deg_vals = df["degradation_pct"].values
    
    print(" -> Applying mechanical wear physics...")
    for i in range(total_rows):
        state = state_vals[i]
        event = event_vals[i]
        deg_pct = deg_vals[i]
        
        if state == "POWER_OFF":
            z_rms[i] = 0.0
            x_rms[i] = 0.0
            z_peak_g[i] = 0.0
            x_peak_g[i] = 0.0
            hf_rms_g[i] = 0.0
            temp_c[i] = 25.0
        elif state == "IDLE" or event == "COLD_START":
            z_rms[i] = 0.5
            x_rms[i] = 0.35
            z_peak_g[i] = 0.05
            x_peak_g[i] = 0.03
            hf_rms_g[i] = 0.05
            temp_c[i] = 40.0
        elif state in ("NORMAL", "CRITICAL"):
            z_rms[i] = base_rms_normal + (deg_pct * degradation_impact_max)
            x_rms[i] = z_rms[i] * 0.7 + np.random.uniform(-0.1, 0.1)
            z_peak_g[i] = 0.1 + (deg_pct * 2.5) + np.random.uniform(-0.05, 0.05)
            x_peak_g[i] = z_peak_g[i] * 0.8 + np.random.uniform(-0.05, 0.05)
            hf_rms_g[i] = 0.1 + (deg_pct * 3.5) + np.random.uniform(-0.05, 0.05)
            temp_c[i] = 60.0 + (deg_pct * 30.0)
            
            if event == "CRITICAL_VIBRATION" and deg_pct == 0:
                z_rms[i] = 7.5
                x_rms[i] = 5.0
                z_peak_g[i] = 2.0
                x_peak_g[i] = 1.5
                hf_rms_g[i] = 2.5
                temp_c[i] = 85.0
    
    # 3. Add sensor noise
    z_rms = np.clip(z_rms + np.random.normal(0, cfg["noise_velocity_abs"], total_rows), 0.0, 25.0)
    x_rms = np.clip(x_rms + np.random.normal(0, cfg["noise_velocity_abs"] * 0.8, total_rows), 0.0, 20.0)
    z_peak_g = np.clip(z_peak_g + np.random.normal(0, 0.02, total_rows), 0.0, 10.0)
    x_peak_g = np.clip(x_peak_g + np.random.normal(0, 0.02, total_rows), 0.0, 8.0)
    hf_rms_g = np.clip(hf_rms_g + np.random.normal(0, 0.02, total_rows), 0.0, 10.0)
    
    # Smooth bearing temperature
    temp_series = pd.Series(temp_c + np.random.normal(0, cfg["noise_temp_abs"], total_rows))
    temp_c = temp_series.rolling(window=15, min_periods=1).mean().values
    
    # 4. Compute ISO zones
    print(" -> Classifying ISO 10816-3 zones...")
    iso_zone = classify_iso_zone(z_rms)
    
    # 5. Kurtosis: derived from ISO zone
    zone_kurt_map = {"ZONE_A": 3.0, "ZONE_B": 4.0, "ZONE_C": 6.0, "ZONE_D": 8.5}
    z_kurtosis = np.array([zone_kurt_map.get(z, 3.0) for z in iso_zone]) + np.random.uniform(-0.3, 0.3, total_rows)
    x_kurtosis = z_kurtosis * 0.85 + np.random.uniform(-0.2, 0.2, total_rows)
    
    # 6. Crest factor: peak / RMS
    z_crest = np.where(hf_rms_g > 0.01, z_peak_g / hf_rms_g, 3.0)
    x_crest = np.where(x_rms > 0.01, x_peak_g / (x_rms * 0.05 + 0.01), 3.0)
    
    # 7. Peak velocity frequency
    peak_freq = np.where(
        np.isin(iso_zone, ["ZONE_A", "ZONE_B"]),
        np.random.uniform(25.0, 50.0, total_rows),
        np.random.uniform(120.0, 300.0, total_rows)
    )
    
    # 8. Format Payload — columns match vibration_schema.json
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "vibration_node",
        "z_axis_rms_velocity_mm_sec": np.round(z_rms, 3),
        "x_axis_rms_velocity_mm_sec": np.round(x_rms, 3),
        "z_axis_peak_acceleration_g": np.round(z_peak_g, 3),
        "x_axis_peak_acceleration_g": np.round(x_peak_g, 3),
        "high_frequency_rms_acceleration_g": np.round(hf_rms_g, 3),
        "z_axis_kurtosis": np.round(z_kurtosis, 2),
        "x_axis_kurtosis": np.round(x_kurtosis, 2),
        "z_axis_crest_factor": np.round(z_crest, 2),
        "x_axis_crest_factor": np.round(x_crest, 2),
        "peak_velocity_component_freq_hz": np.round(peak_freq, 1),
        "temperature_c": np.round(temp_c, 2),
        "iso_health_zone": iso_zone,
        "data_source": "synthetic",
        "machine_state": df["machine_state"],
        "active_event": df["active_event"],
        "degradation_pct": df["degradation_pct"],
    })
    
    payload_df.to_parquet("output/vibration_data.parquet")
    payload_df.head(1000).to_csv("output/vibration_data_sample.csv", index=False)
    
    print(f"  Generated {len(payload_df):,} vibration records (13 schema fields).")
    
    return payload_df

if __name__ == "__main__":
    generate_vibration_data()
