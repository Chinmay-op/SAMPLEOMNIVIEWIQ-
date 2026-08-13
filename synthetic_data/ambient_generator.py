# ============================================================
# OmniView IQ POC — Ambient Weather Generator
# Generates the 15-day weather cycle + daily fluctuations.
# Polled every 2 minutes. Used by other generators for baseline shifts.
# ============================================================

import pandas as pd
import numpy as np
from datetime import datetime
import os
from config import LAYER_0

def generate_ambient_data(timeline_path="timeline.parquet"):
    """
    Reads the master timeline and generates 2-minute ambient readings.
    """
    print("Generating Ambient Weather data...")
    cfg = LAYER_0["ambient"]
    
    # In a real pipeline, we'd read the parquet. Here we generate the timestamps directly
    # since ambient has no dependency on machine state, only time.
    start_dt = datetime.fromisoformat(LAYER_0["simulation_start"])
    total_days = LAYER_0["simulation_days"]
    total_minutes = total_days * 1440
    
    # Polling every 2 minutes
    timestamps = [start_dt + pd.Timedelta(minutes=i) for i in range(0, total_minutes, 2)]
    
    # 1. 15-17 day seasonal cycle (sinusoidal)
    cycle_days = cfg["cycle_days"]
    days_elapsed = np.array([i / (60 * 24) for i in range(0, total_minutes, 2)])
    
    seasonal_temp_shift = np.sin(days_elapsed * (2 * np.pi / cycle_days)) * cfg["annual_temp_amplitude"]
    seasonal_humidity_shift = np.cos(days_elapsed * (2 * np.pi / cycle_days)) * cfg["humidity_amplitude_pct"]
    
    # 2. Daily day/night cycle
    # Peak temp around 14:00 (14/24), lowest around 04:00
    daily_phase = ((days_elapsed % 1) - (14/24)) * 2 * np.pi
    daily_temp_swing = np.cos(daily_phase) * cfg["daily_temp_variation"]
    
    # Humidity usually inversely proportional to temp during the day
    daily_humidity_swing = -np.cos(daily_phase) * 10.0 
    
    # 3. Base Math
    base_temp = cfg["annual_temp_mean"] + seasonal_temp_shift + daily_temp_swing
    base_humidity = cfg["humidity_mean_pct"] + seasonal_humidity_shift + daily_humidity_swing
    
    # 4. Add Noise
    temp_noise = np.random.normal(0, cfg["noise_temp_abs"], len(timestamps))
    humidity_noise = np.random.normal(0, cfg["noise_humidity_abs"], len(timestamps))
    
    final_temp = np.clip(base_temp + temp_noise, 10.0, 45.0)  # Pune bounds
    final_humidity = np.clip(base_humidity + humidity_noise, 20.0, 95.0)
    
    # 5. Assemble Payload
    df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": timestamps,
        "sensor_type": "ambient_weather",
        "ambient_temp_c": np.round(final_temp, 2),
        "ambient_humidity_pct": np.round(final_humidity, 2)
    })
    
    # Ensure export directory exists
    os.makedirs("output", exist_ok=True)
    
    # Save files
    df.to_parquet("output/ambient_data.parquet")
    df.head(1000).to_csv("output/ambient_data_sample.csv", index=False)
    
    print(f"✅ Generated {len(df):,} ambient records.")
    print(f"   Temp range: {df['ambient_temp_c'].min()}°C to {df['ambient_temp_c'].max()}°C")
    print(f"   Humidity range: {df['ambient_humidity_pct'].min()}% to {df['ambient_humidity_pct'].max()}%")
    
    return df

if __name__ == "__main__":
    generate_ambient_data()
