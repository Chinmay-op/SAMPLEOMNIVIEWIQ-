# ============================================================
# OmniView IQ POC — Vibration Generator
# Polls every 60 seconds. Simulates mechanical wear over 
# 14+ day degradation windows (Zone A -> D).
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def generate_vibration_data():
    print("Generating Vibration data...")
    cfg = LAYER_0["vibration"]
    
    # 1. Load Master Timeline
    df = pd.read_parquet("output/master_timeline.parquet")
    total_rows = len(df)
    
    # Initialize arrays
    rms = np.zeros(total_rows)
    bearing_temp = np.zeros(total_rows)
    
    # 2. Extract physics params
    zone_b_thresh = cfg["zone_a_max"]       # Zone A/B boundary: 2.8 mm/s
    zone_c_thresh = cfg["zone_b_max"]       # Zone B/C boundary: 7.1 mm/s
    zone_d_thresh = cfg["zone_c_max"]       # Zone C/D boundary: 18.0 mm/s
    
    # 3. Handle Degradation Curve
    # The timeline already has 'degradation_pct' mapped from 0.0 to 1.0 over the 14-day window.
    # We will use this to scale the base vibration up.
    
    base_rms_normal = 1.5                   # Zone A healthy baseline (mm/s)
    # At 100% degradation, RMS should be deeply into Zone D (e.g., 6.0+)
    degradation_impact_max = 5.5 
    
    print(" -> Applying mechanical wear physics...")
    for i in range(total_rows):
        state = df["machine_state"].iloc[i]
        event = df["active_event"].iloc[i]
        deg_pct = df["degradation_pct"].iloc[i]
        
        if state == "POWER_OFF":
            rms[i] = 0.0
            bearing_temp[i] = 25.0  # Cool down to ambient
        elif state == "IDLE" or event == "COLD_START":
            rms[i] = 0.5  # Minor hum from background factory noise
            bearing_temp[i] = 40.0
        elif state == "NORMAL" or state == "CRITICAL":
            # Base running vibration + degradation scaling
            rms[i] = base_rms_normal + (deg_pct * degradation_impact_max)
            
            # Bearing temperature rises as friction increases (degradation)
            bearing_temp[i] = 60.0 + (deg_pct * 30.0) 
            
            # If there's an instant critical event (e.g. broken tooth, not just wear)
            if event == "CRITICAL_VIBRATION" and deg_pct == 0:
                rms[i] = 7.5
                bearing_temp[i] = 85.0
                
    # 4. Add high-frequency sensor noise
    noise_rms = np.random.normal(0, cfg["noise_velocity_abs"], total_rows)
    noise_temp = np.random.normal(0, cfg["noise_temp_abs"], total_rows)
    
    rms = np.clip(rms + noise_rms, 0.0, 15.0)
    
    # Bearing takes time to heat up/cool down, smooth it out slightly
    df["surface_temperature_c"] = bearing_temp + noise_temp
    df["surface_temperature_c"] = df["surface_temperature_c"].rolling(window=15, min_periods=1).mean().round(2)
    df["rms_velocity_mm_s"] = np.round(rms, 3)
    
    # 5. Compute Edge-Derived ISO Zones
    print(" -> Classifying ISO 10816-3 zones...")
    df["iso_health_zone"] = np.where(
        df["rms_velocity_mm_s"] >= zone_d_thresh, "ZONE_D",
        np.where(df["rms_velocity_mm_s"] >= zone_c_thresh, "ZONE_C",
        np.where(df["rms_velocity_mm_s"] >= zone_b_thresh, "ZONE_B", "ZONE_A"))
    )
    
    # 6. Compute Trends (10 min rolling slope)
    df["vibration_diff_10min"] = df["rms_velocity_mm_s"].diff(10)
    df["temp_diff_10min"] = df["surface_temperature_c"].diff(10)
    
    df["vibration_trend_10min"] = np.where(
        df["vibration_diff_10min"] > 0.3, "RISING",
        np.where(df["vibration_diff_10min"] < -0.3, "FALLING", "STABLE")
    )
    
    df["temp_trend_10min"] = np.where(
        df["temp_diff_10min"] > 2.0, "RISING",
        np.where(df["temp_diff_10min"] < -2.0, "FALLING", "STABLE")
    )
    
    # 7. Format Payload
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": df["timestamp"],
        "sensor_type": "vibration_node",
        "rms_velocity_mm_s": df["rms_velocity_mm_s"],
        "surface_temperature_c": df["surface_temperature_c"],
        "iso_health_zone": df["iso_health_zone"],
        "vibration_trend_10min": df["vibration_trend_10min"],
        "temp_trend_10min": df["temp_trend_10min"],
        "machine_state": df["machine_state"], # Ground truth
        "active_event": df["active_event"],   # Ground truth
        "degradation_pct": df["degradation_pct"] # Ground truth
    })
    
    payload_df.to_parquet("output/vibration_data.parquet")
    payload_df.head(1000).to_csv("output/vibration_data_sample.csv", index=False)
    
    print(f"✅ Generated {len(payload_df):,} vibration records.")
    
    return payload_df

if __name__ == "__main__":
    generate_vibration_data()
