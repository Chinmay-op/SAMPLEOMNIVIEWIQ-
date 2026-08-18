# ============================================================
# OmniView IQ POC — Electrical Generator (Selec MFM384)
# Polls every 15 seconds. Full per-phase 3-phase power metering.
# OUTPUT COLUMNS: Match electrical_schema.json exactly (27 fields).
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
    upsampled_df = merged_df.resample("15s").ffill().reset_index()
    total_rows = len(upsampled_df)
    
    # Initialize base arrays
    voltage_ll = np.full(total_rows, float(cfg["normal_voltage_v"]))
    current_avg = np.zeros(total_rows)
    kva = np.zeros(total_rows)
    pf_avg = np.zeros(total_rows)
    thd_i = np.zeros(total_rows)
    
    # 4. Generate Base ISBM Machine Load by state
    print(" -> Simulating ISBM load...")
    is_normal = upsampled_df["machine_state"] == "NORMAL"
    is_critical = upsampled_df["machine_state"] == "CRITICAL"
    is_running = is_normal | is_critical
    is_idle = upsampled_df["machine_state"] == "IDLE"
    is_power_off = upsampled_df["machine_state"] == "POWER_OFF"
    
    # Normal/Critical base values
    kva[is_running] = np.random.uniform(cfg["normal_kva_min"], cfg["normal_kva_max"], np.sum(is_running))
    pf_avg[is_running] = np.random.uniform(cfg["normal_pf_min"], cfg["normal_pf_max"], np.sum(is_running))
    thd_i[is_running] = np.random.uniform(cfg["normal_thd_min"], cfg["normal_thd_max"], np.sum(is_running))
    current_avg[is_running] = np.random.uniform(cfg["normal_current_min"], cfg["normal_current_max"], np.sum(is_running))
    
    # Idle base values
    kva[is_idle] = np.random.uniform(0, cfg["idle_kva_max"], np.sum(is_idle))
    pf_avg[is_idle] = np.random.uniform(0.70, 0.85, np.sum(is_idle))
    thd_i[is_idle] = np.random.uniform(2.0, 4.0, np.sum(is_idle))
    current_avg[is_idle] = np.random.uniform(20, cfg["idle_current_max"], np.sum(is_idle))
    
    # Power Off base values
    kva[is_power_off] = np.random.uniform(0, cfg["power_off_kva_max"], np.sum(is_power_off))
    pf_avg[is_power_off] = 0.95
    thd_i[is_power_off] = 1.0
    current_avg[is_power_off] = np.random.uniform(0, 10, np.sum(is_power_off))
    
    # 5. Add Compressor Load (Sync'd with pressure cycles)
    print(" -> Syncing Compressor load...")
    is_comp_loaded = upsampled_df["compressor_state"] == "LOADED"
    kva[is_comp_loaded] += 50.0
    current_avg[is_comp_loaded] += 65.0
    
    # 6. Apply MD Breach Math
    print(" -> Applying MD Breach math...")
    md_risk_mask = upsampled_df["active_event"].isin(["MD_BREACH_RISK", "MD_BREACH_CRITICAL"])
    in_event = False
    event_start_idx = 0
    for i in range(total_rows):
        if md_risk_mask.iloc[i]:
            if not in_event:
                in_event = True
                event_start_idx = i
            ticks_elapsed = i - event_start_idx
            climb_factor = min(ticks_elapsed * 1.5, 120.0)
            kva[i] += climb_factor
            current_avg[i] += (climb_factor * 1.3)
        else:
            in_event = False
    
    # === DERIVE ALL 27 SCHEMA FIELDS ===
    
    # Voltage Line-to-Neutral
    v_ln_avg = voltage_ll / 1.732
    
    # Per-phase voltages with imbalance
    imb_v1 = np.random.normal(0, 0.008, total_rows)
    imb_v2 = np.random.normal(0, 0.008, total_rows)
    v_l1 = v_ln_avg * (1.0 + imb_v1)
    v_l2 = v_ln_avg * (1.0 + imb_v2)
    v_l3 = 3.0 * v_ln_avg - v_l1 - v_l2
    
    # Per-phase currents with load imbalance
    imb_i1 = np.random.normal(0, 0.03, total_rows)
    imb_i2 = np.random.normal(0, 0.03, total_rows)
    i_l1 = current_avg * (1.0 + imb_i1)
    i_l2 = current_avg * (1.0 + imb_i2)
    i_l3 = 3.0 * current_avg - i_l1 - i_l2
    i_neutral = np.abs(i_l1 - i_l2) * np.random.uniform(0.10, 0.25, total_rows)
    
    # Power calculations
    kw = kva * pf_avg
    kvar = np.sqrt(np.maximum(0, kva**2 - kw**2))
    
    # Per-phase kW
    imb_p = np.random.normal(0, 0.02, total_rows)
    kw_l1 = (kw / 3.0) * (1.0 + imb_p)
    kw_l2 = (kw / 3.0) * (1.0 + np.random.normal(0, 0.02, total_rows))
    kw_l3 = kw - kw_l1 - kw_l2
    
    # Per-phase power factor
    pf_l1 = np.clip(np.abs(pf_avg + np.random.normal(0, 0.01, total_rows)), 0.1, 1.0)
    pf_l2 = np.clip(np.abs(pf_avg + np.random.normal(0, 0.01, total_rows)), 0.1, 1.0)
    pf_l3 = np.clip(np.abs(pf_avg + np.random.normal(0, 0.01, total_rows)), 0.1, 1.0)
    
    # Frequency
    frequency = 50.0 + np.random.uniform(-0.2, 0.2, total_rows)
    
    # Voltage THD (usually lower than current THD)
    thd_v = 2.0 + (np.clip(kw / 200.0, 0, 1) * 3.0) + np.random.uniform(-0.3, 0.3, total_rows)
    
    # Cumulative energy
    energy_increment = kw * (15.0 / 3600.0)  # kWh per 15-second interval
    active_energy_kwh = np.cumsum(energy_increment) + 150000.0
    apparent_energy_kvah = active_energy_kwh * 1.05
    
    # Add noise
    voltage_ll += np.random.normal(0, cfg["noise_voltage_abs"], total_rows)
    kva = kva * (1 + np.random.normal(0, cfg["noise_kva_pct"], total_rows))
    kw = kva * pf_avg  # recalculate
    current_avg = np.clip(current_avg, 0, 1200)
    
    # Edge-computed: rolling kVA and MD proximity
    print(" -> Computing Edge MD derivations...")
    upsampled_df["kva_temp"] = np.round(kva, 2)
    rolling_kva = upsampled_df["kva_temp"].rolling(window=60, min_periods=1).mean().values
    contracted_md = cfg["contracted_demand_kva"]
    md_proximity = np.round((rolling_kva / contracted_md) * 100, 2)
    
    # 7. Format Payload — columns match electrical_schema.json exactly
    payload_df = pd.DataFrame({
        "device_id": LAYER_0["device_id"],
        "timestamp": upsampled_df["timestamp"],
        "sensor_type": "electrical_meter",
        "voltage_v_ln_avg": np.round(v_ln_avg, 2),
        "voltage_v_ll_avg": np.round(voltage_ll, 2),
        "voltage_v_l1_n": np.round(v_l1, 2),
        "voltage_v_l2_n": np.round(v_l2, 2),
        "voltage_v_l3_n": np.round(v_l3, 2),
        "current_a_avg": np.round(current_avg, 2),
        "current_a_l1": np.round(i_l1, 2),
        "current_a_l2": np.round(i_l2, 2),
        "current_a_l3": np.round(i_l3, 2),
        "current_a_neutral": np.round(i_neutral, 2),
        "active_power_kw_total": np.round(kw, 2),
        "active_power_kw_l1": np.round(kw_l1, 2),
        "active_power_kw_l2": np.round(kw_l2, 2),
        "active_power_kw_l3": np.round(kw_l3, 2),
        "apparent_power_kva_total": np.round(kva, 2),
        "reactive_power_kvar_total": np.round(kvar, 2),
        "power_factor_avg": np.round(np.clip(pf_avg, 0.1, 1.0), 3),
        "power_factor_l1": np.round(pf_l1, 3),
        "power_factor_l2": np.round(pf_l2, 3),
        "power_factor_l3": np.round(pf_l3, 3),
        "frequency_hz": np.round(frequency, 2),
        "voltage_thd_percent": np.round(np.clip(thd_v, 0, 15), 2),
        "current_thd_percent": np.round(np.clip(thd_i, 0, 20), 2),
        "active_energy_kwh": np.round(active_energy_kwh, 2),
        "apparent_energy_kvah": np.round(apparent_energy_kvah, 2),
        "rolling_kva_15min": np.round(rolling_kva, 2),
        "md_proximity_percent": md_proximity,
        "machine_state": upsampled_df["machine_state"],
        "active_event": upsampled_df["active_event"],
    })
    
    payload_df.to_parquet("output/electrical_data.parquet")
    payload_df.head(1000).to_csv("output/electrical_data_sample.csv", index=False)
    
    # Export shared state for cross-sensor generators
    cross_sensor_df = pd.DataFrame({
        "timestamp": upsampled_df["timestamp"],
        "current_a_avg": np.round(current_avg, 2),
        "active_power_kw_total": np.round(kw, 2),
    })
    cross_sensor_df.to_parquet("output/electrical_cross_sensor.parquet")
    
    print(f"  Generated {len(payload_df):,} electrical records (27 schema fields).")
    print(f"  Columns: {[c for c in payload_df.columns if c not in ['machine_state','active_event','device_id','timestamp','sensor_type']]}")
    
    return payload_df

if __name__ == "__main__":
    generate_electrical_data()
