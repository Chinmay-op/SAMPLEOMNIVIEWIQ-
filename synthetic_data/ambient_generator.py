# ============================================================
# OmniView IQ POC — Ambient Weather Generator
# Generates the 15-day weather cycle + daily fluctuations.
# Polled every 2 minutes. Used by other generators for baseline shifts.
# OUTPUT COLUMNS: Match ambient_schema.json exactly.
# ============================================================

import pandas as pd
import numpy as np
import math
from datetime import datetime
import os
from config import LAYER_0

def generate_ambient_data(timeline_path="timeline.parquet"):
    """
    Reads the master timeline and generates 2-minute ambient readings.
    All output columns match schemas/ambient_schema.json.
    """
    print("Generating Ambient Weather data...")
    cfg = LAYER_0["ambient"]
    
    start_dt = datetime.fromisoformat(LAYER_0["simulation_start"])
    total_days = LAYER_0["simulation_days"]
    total_minutes = total_days * 1440
    
    # Polling every 2 minutes
    timestamps = [start_dt + pd.Timedelta(minutes=i) for i in range(0, total_minutes, 2)]
    n = len(timestamps)
    
    # 1. 15-17 day seasonal cycle (sinusoidal)
    cycle_days = cfg["cycle_days"]
    days_elapsed = np.array([i / (60 * 24) for i in range(0, total_minutes, 2)])
    
    seasonal_temp_shift = np.sin(days_elapsed * (2 * np.pi / cycle_days)) * cfg["annual_temp_amplitude"]
    seasonal_humidity_shift = np.cos(days_elapsed * (2 * np.pi / cycle_days)) * cfg["humidity_amplitude_pct"]
    
    # 2. Daily day/night cycle
    daily_phase = ((days_elapsed % 1) - (14/24)) * 2 * np.pi
    daily_temp_swing = np.cos(daily_phase) * cfg["daily_temp_variation"]
    daily_humidity_swing = -np.cos(daily_phase) * 10.0 
    
    # 3. Base Math
    base_temp = cfg["annual_temp_mean"] + seasonal_temp_shift + daily_temp_swing
    base_humidity = cfg["humidity_mean_pct"] + seasonal_humidity_shift + daily_humidity_swing
    
    # 4. Add Noise
    temp_noise = np.random.normal(0, cfg["noise_temp_abs"], n)
    humidity_noise = np.random.normal(0, cfg["noise_humidity_abs"], n)
    
    final_temp = np.clip(base_temp + temp_noise, 10.0, 45.0)
    final_humidity = np.clip(base_humidity + humidity_noise, 20.0, 95.0)
    
    # 5. Compute Dew Point (Magnus formula)
    a = 17.27
    b = 237.7
    alpha = (a * final_temp) / (b + final_temp) + np.log(np.clip(final_humidity, 1.0, 100.0) / 100.0)
    dew_point = np.round((b * alpha) / (a - alpha), 2)
    
    # 6. Compute Heat Index (simplified Steadman formula)
    e = (final_humidity / 100.0) * 6.105 * np.exp((a * final_temp) / (b + final_temp))
    heat_index = np.round(final_temp + 0.33 * e - 0.70 * 0.5 - 4.0, 2)
    
    # 7. Wireless RSSI: degrades with temperature (more EMI from hot equipment)
    rssi = np.round(-65 - (final_temp - 25.0) * 0.3 + np.random.uniform(-3, 3, n)).astype(int)
    
    # 8. Environmental Baseline Offset: normalizes around 25C
    offset = np.round(np.maximum(0.5, 1.0 + ((final_temp - 25.0) * 0.05)), 2)
    
    # 9. Assemble Payload — columns match ambient_schema.json
    df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": timestamps,
        "sensor_type": "ambient_weather",
        "ambient_temp_c": np.round(final_temp, 2),
        "relative_humidity_pct": np.round(final_humidity, 2),
        "dew_point_c": dew_point,
        "heat_index_c": heat_index,
        "wireless_signal_strength_dbm": rssi,
        "environmental_baseline_offset": offset,
    })
    
    os.makedirs("output", exist_ok=True)
    df.to_parquet("output/ambient_data.parquet")
    df.head(1000).to_csv("output/ambient_data_sample.csv", index=False)
    
    print(f"  Generated {len(df):,} ambient records.")
    print(f"  Temp range: {df['ambient_temp_c'].min()} to {df['ambient_temp_c'].max()} C")
    print(f"  Humidity range: {df['relative_humidity_pct'].min()}% to {df['relative_humidity_pct'].max()}%")
    print(f"  Columns: {list(df.columns)}")
    
    return df

if __name__ == "__main__":
    generate_ambient_data()
