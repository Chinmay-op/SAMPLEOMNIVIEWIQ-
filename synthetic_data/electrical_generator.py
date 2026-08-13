# ============================================================
# OmniView IQ POC — Electrical Generator
# Polls every 15 seconds. Combines ISBM baseline load with 
# the Compressor sync timeline to ensure physical accuracy.
# Handles MD Breach integration math.
# ============================================================

import pandas as pd
import numpy as np
import os
from config import LAYER_0

def generate_electrical_data():
    print("Generating Electrical data (15-second resolution)...")
    cfg = LAYER_0["electrical"]
    
    # 1. Load Master Timeline (1 min resolution)
    timeline_df = pd.read_parquet("output/master_timeline.parquet")
    
    # 2. Load Compressor Sync Timeline (1 min resolution)
    comp_df = pd.read_parquet("output/compressor_sync.parquet")
    
    # Merge them
    merged_df = pd.merge(timeline_df, comp_df, on="timestamp")
    
    # 3. Upsample to 15-second resolution
    merged_df.set_index("timestamp", inplace=True)
    # Resample and forward fill the states
    upsampled_df = merged_df.resample("15s").ffill().reset_index()
    total_rows = len(upsampled_df)
    
    # Initialize arrays for electrical values
    voltage = np.full(total_rows, float(cfg["normal_voltage_v"]))
    kva = np.zeros(total_rows)
    kw = np.zeros(total_rows)
    pf = np.zeros(total_rows)
    current = np.zeros(total_rows)
    thd = np.zeros(total_rows)
    
    # 4. Generate Base ISBM Machine Load
    print(" -> Simulating ISBM load...")
    is_normal = upsampled_df["machine_state"] == "NORMAL"
    is_idle = upsampled_df["machine_state"] == "IDLE"
    is_power_off = upsampled_df["machine_state"] == "POWER_OFF"
    
    # Normal base values (Random walk within band)
    kva[is_normal] = np.random.uniform(cfg["normal_kva_min"], cfg["normal_kva_max"], np.sum(is_normal))
    pf[is_normal] = np.random.uniform(cfg["normal_pf_min"], cfg["normal_pf_max"], np.sum(is_normal))
    thd[is_normal] = np.random.uniform(cfg["normal_thd_min"], cfg["normal_thd_max"], np.sum(is_normal))
    current[is_normal] = np.random.uniform(cfg["normal_current_min"], cfg["normal_current_max"], np.sum(is_normal))
    
    # Idle base values
    kva[is_idle] = np.random.uniform(0, cfg["idle_kva_max"], np.sum(is_idle))
    pf[is_idle] = np.random.uniform(0.70, 0.85, np.sum(is_idle)) # PF usually drops when idling
    thd[is_idle] = np.random.uniform(2.0, 4.0, np.sum(is_idle))
    current[is_idle] = np.random.uniform(20, 80, np.sum(is_idle))
    
    # Power Off base values
    kva[is_power_off] = np.random.uniform(0, cfg["power_off_kva_max"], np.sum(is_power_off))
    pf[is_power_off] = 0.95
    thd[is_power_off] = 1.0
    current[is_power_off] = np.random.uniform(0, 10, np.sum(is_power_off))
    
    # 5. Add Compressor Load (Sync'd with pressure cycles)
    print(" -> Syncing Compressor load...")
    is_comp_loaded = upsampled_df["compressor_state"] == "LOADED"
    
    # When compressor is loaded, add a static heavy load block
    kva[is_comp_loaded] += 50.0  # +50 kVA
    current[is_comp_loaded] += 65.0 # +65 Amps
    
    # 6. Apply MD Breach Math (Sustained climbing curve, not random noise)
    print(" -> Applying MD Breach math...")
    # Find segments where active_event is MD_BREACH_RISK or MD_BREACH_CRITICAL
    md_risk_mask = upsampled_df["active_event"].isin(["MD_BREACH_RISK", "MD_BREACH_CRITICAL"])
    
    # We want kVA to climb linearly during an MD event window
    in_event = False
    event_start_idx = 0
    for i in range(total_rows):
        if md_risk_mask.iloc[i]:
            if not in_event:
                in_event = True
                event_start_idx = i
            # Increase kVA over time. 15 mins = 60 ticks. 
            # We want to push the baseline kVA up by about 100 kVA over 15 mins to guarantee a breach.
            ticks_elapsed = i - event_start_idx
            climb_factor = min(ticks_elapsed * 1.5, 120.0) # Cap the climb
            kva[i] += climb_factor
            current[i] += (climb_factor * 1.3) # Current scales roughly with kVA
        else:
            in_event = False
            
    # Calculate KW based on final KVA and PF
    kw = kva * pf
    
    # 7. Add noise to everything to make it look like real sensors
    voltage += np.random.normal(0, cfg["noise_voltage_abs"], total_rows)
    kva = kva * (1 + np.random.normal(0, cfg["noise_kva_pct"], total_rows))
    kw = kva * pf # recalculate
    current = current * (1 + np.random.normal(0, cfg["noise_current_pct"], total_rows))
    
    # Clip to physical boundaries
    upsampled_df["voltage_v"] = np.round(np.clip(voltage, 400, 430), 2)
    upsampled_df["apparent_power_kva"] = np.round(np.clip(kva, 0, 1000), 2)
    upsampled_df["active_power_kw"] = np.round(np.clip(kw, 0, 1000), 2)
    upsampled_df["power_factor"] = np.round(np.clip(pf, 0.1, 1.0), 3)
    upsampled_df["current_a"] = np.round(np.clip(current, 0, 1200), 2)
    upsampled_df["thd_current_percent"] = np.round(np.clip(thd, 0, 20), 2)
    
    # 8. Compute Edge-Derived rolling averages (The 15-minute MD window)
    print(" -> Computing Edge MD derivations...")
    # 15 minutes = 60 readings at 15s intervals
    upsampled_df["rolling_kva_15min"] = upsampled_df["apparent_power_kva"].rolling(window=60, min_periods=1).mean().round(2)
    
    contracted_md = cfg["contracted_demand_kva"]
    upsampled_df["md_proximity_percent"] = np.round((upsampled_df["rolling_kva_15min"] / contracted_md) * 100, 2)
    
    # 9. Format Payload
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": upsampled_df["timestamp"],
        "sensor_type": "electrical_meter",
        "voltage_v": upsampled_df["voltage_v"],
        "current_a": upsampled_df["current_a"],
        "active_power_kw": upsampled_df["active_power_kw"],
        "apparent_power_kva": upsampled_df["apparent_power_kva"],
        "power_factor": upsampled_df["power_factor"],
        "thd_current_percent": upsampled_df["thd_current_percent"],
        "rolling_kva_15min": upsampled_df["rolling_kva_15min"],
        "md_proximity_percent": upsampled_df["md_proximity_percent"],
        "machine_state": upsampled_df["machine_state"], # Ground truth
        "active_event": upsampled_df["active_event"]    # Ground truth
    })
    
    payload_df.to_parquet("output/electrical_data.parquet")
    payload_df.head(1000).to_csv("output/electrical_data_sample.csv", index=False)
    
    print(f"✅ Generated {len(payload_df):,} electrical records.")
    
    return payload_df

if __name__ == "__main__":
    generate_electrical_data()
